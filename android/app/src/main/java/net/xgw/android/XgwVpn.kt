package net.xgw.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.VpnService
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import org.json.JSONObject

/**
 * VPN телефона (А3): интерфейс VpnService, весь трафик телефона — в Xray, запущенный
 * отдельным процессом с дескриптором интерфейса (Native, xgwrun.c). Само приложение
 * исключено из своего VPN: его запросы к шлюзу (Funnel) и соединения Xray с серверами идут
 * напрямую — процесс Xray работает под тем же пользователем Android.
 *
 * Xray завершился сам — перезапуск (до трёх раз подряд); не поднялся — VPN выключается с
 * уведомлением: пока интерфейс открыт, а Xray нет, у телефона нет интернета.
 */
class XgwVpn : VpnService() {
    companion object {
        const val START = "net.xgw.android.vpn.START"
        const val STOP = "net.xgw.android.vpn.STOP"
        const val RELOAD = "net.xgw.android.vpn.RELOAD"
        private const val CHANNEL = "vpn"
        private const val NOTE = 1
        private const val ADDRESS = "10.233.233.1"
        private const val DNS = "10.233.233.2"
        private const val ADDRESS6 = "fd00:7867:7767::1"
        private const val RESTARTS = 3

        /** Состояние для экрана: off, starting, on, error. */
        @Volatile var state: String = "off"
            private set
        @Volatile var detail: String = ""
            private set
        @Volatile var since: Long = 0L
            private set

        fun snapshot(): JSONObject = JSONObject().put("state", state).put("detail", detail).put("since", since)

        fun send(context: Context, action: String) {
            val intent = Intent(context, XgwVpn::class.java).setAction(action)
            if (action == START) context.startForegroundService(intent) else context.startService(intent)
        }

        private fun mark(value: String, text: String = "") {
            if (value != state) since = System.currentTimeMillis()
            state = value
            detail = text
        }
    }

    private lateinit var xray: PhoneXray
    private var tun: ParcelFileDescriptor? = null
    private var runner: Thread? = null
    @Volatile private var pid = 0
    @Volatile private var stopping = false
    @Volatile private var reloading = false

    override fun onCreate() {
        super.onCreate()
        xray = PhoneXray(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            STOP -> {
                shutdown("off", "")
                return START_NOT_STICKY
            }
            RELOAD -> {
                reload()
                return START_STICKY
            }
        }
        // START из приложения или запуск системой («VPN всегда», после перезагрузки).
        foreground("Включаю VPN…")
        if (runner?.isAlive == true) return START_STICKY
        if (xray.info() == null) {
            shutdown("error", "Нет списка серверов: откройте приложение, пока есть связь со шлюзом")
            return START_NOT_STICKY
        }
        val problem = try {
            xray.prepare()
            establish()
        } catch (exc: Exception) {
            exc.message ?: exc.javaClass.simpleName
        }
        if (problem.isNotEmpty()) {
            shutdown("error", problem)
            return START_NOT_STICKY
        }
        stopping = false
        mark("starting", "Запускаю Xray…")
        runner = Thread({ loop() }, "xray").apply { start() }
        return START_STICKY
    }

    override fun onRevoke() {
        // Разрешение отозвано: включён другой VPN или выключено в настройках Android.
        shutdown("off", "VPN выключен в Android или включён другой VPN")
    }

    override fun onDestroy() {
        if (state == "on" || state == "starting") shutdown("off", "")
        super.onDestroy()
    }

    private fun establish(): String {
        val builder = Builder()
            .setSession("XGW")
            .setMtu(1500)
            .addAddress(ADDRESS, 30)
            .addRoute("0.0.0.0", 0)
            .addAddress(ADDRESS6, 126)
            .addRoute("::", 0)
            .addDnsServer(DNS)
            .addDisallowedApplication(packageName)
            .setConfigureIntent(screen())
        builder.setUnderlyingNetworks(null)
        tun = builder.establish() ?: return "Android не дал разрешения на VPN: включите VPN в приложении ещё раз"
        return ""
    }

    /** Поток Xray: запуск, ожидание, перезапуск. PR_SET_PDEATHSIG в xgwrun.c — к этому потоку. */
    private fun loop() {
        var failures = 0
        while (!stopping) {
            val fd = tun?.fd ?: break
            val started = SystemClock.elapsedRealtime()
            val argv = arrayOf(xray.exe, "run", "-config", xray.config.path)
            val child = Native.start(argv, xray.env(), fd, xray.log.path)
            if (child < 0) {
                fail("Xray не запустился (ошибка ${-child})")
                return
            }
            pid = child
            mark("on", "")
            notifyOn()
            val code = Native.waitFor(child)
            pid = 0
            if (stopping) break
            if (reloading) {
                reloading = false
                mark("starting", "Новый список серверов — перезапускаю Xray…")
                continue
            }
            if (SystemClock.elapsedRealtime() - started > 60_000) failures = 0
            failures += 1
            val why = if (code > 128) "остановлен (сигнал ${code - 128})" else "завершился (код $code)"
            if (failures > RESTARTS) {
                val errors = xray.errors()
                fail("Xray $why ${RESTARTS + 1} раза подряд — VPN выключен, чтобы телефон не остался " +
                    "без интернета" + if (errors.isNotEmpty()) ". Xray: $errors" else "")
                return
            }
            mark("starting", "Xray $why — перезапускаю…")
            SystemClock.sleep(2_000L * failures)
        }
    }

    /** Новый конфиг сохранён: перезапустить Xray на нём (интерфейс VPN остаётся). */
    private fun reload() {
        val current = pid
        if (current <= 0 || stopping) return
        reloading = true
        Native.stop(current)
    }

    private fun fail(text: String) {
        android.os.Handler(mainLooper).post { shutdown("error", text) }
    }

    private fun shutdown(value: String, text: String) {
        stopping = true
        val current = pid
        if (current > 0) Native.stop(current)
        runner?.let { thread ->
            if (thread !== Thread.currentThread()) {
                thread.join(3_000)
                if (thread.isAlive && pid > 0) android.os.Process.killProcess(pid)
            }
        }
        runner = null
        try {
            tun?.close()
        } catch (exc: Exception) {
            // интерфейс уже закрыт
        }
        tun = null
        mark(value, text)
        stopForeground(STOP_FOREGROUND_REMOVE)
        if (value == "error") notifyError(text)
        stopSelf()
    }

    private fun screen(): PendingIntent = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
    )

    private fun channel(): NotificationManager {
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(CHANNEL) == null) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, "VPN XGW", NotificationManager.IMPORTANCE_LOW),
            )
        }
        return manager
    }

    private fun note(text: String, ongoing: Boolean): Notification {
        channel()
        val builder = Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_vpn)
            .setContentTitle("VPN XGW")
            .setContentText(text)
            .setContentIntent(screen())
            .setOngoing(ongoing)
        if (ongoing) {
            val off = PendingIntent.getService(
                this, 1, Intent(this, XgwVpn::class.java).setAction(STOP), PendingIntent.FLAG_IMMUTABLE,
            )
            builder.addAction(Notification.Action.Builder(null, "Выключить", off).build())
        }
        return builder.build()
    }

    private fun foreground(text: String) {
        startForeground(NOTE, note(text, true), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
    }

    private fun notifyOn() {
        val servers = xray.info()?.optInt("servers") ?: 0
        channel().notify(NOTE, note("Включён: серверов $servers", true))
    }

    private fun notifyError(text: String) {
        channel().notify(NOTE + 1, note("VPN выключен: $text", false))
    }
}
