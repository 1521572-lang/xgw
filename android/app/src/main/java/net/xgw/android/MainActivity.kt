package net.xgw.android

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.NotificationManager
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.provider.Settings
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.window.OnBackInvokedDispatcher
import com.google.mlkit.common.MlKitException
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import org.json.JSONObject
import java.util.Base64
import java.util.concurrent.Executors

/**
 * Экран приложения — страница из assets (index.html, app.js) в WebView. Страница не ходит в
 * сеть сама: запросы к шлюзу, подпись и Keystore — здесь, через мост [Bridge].
 * Всё, что приходит от шлюза, страница вставляет только как текст.
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var keys: Keys
    private lateinit var xray: PhoneXray
    private val worker = Executors.newSingleThreadExecutor()
    @Volatile private var pendingLink = ""
    private var loaded = false
    private var vpnRequest = 0 // номер ответа странице, пока Android спрашивает разрешение на VPN
    private var notesRequest = 0 // то же — пока спрашивает разрешение на уведомления

    private companion object {
        const val ASK_VPN = 1
        const val ASK_NOTES = 2
        /** Имя файла записи трафика — как record._NAME на шлюзе. */
        val RECORD = Regex("[0-9a-f]{12}-[0-9]{8}-[0-9]{6}[.]pcap")
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        keys = Keys(this)
        xray = PhoneXray(this)
        web = WebView(this)
        web.settings.apply {
            javaScriptEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            setSupportZoom(false)
        }
        web.webViewClient = object : WebViewClient() {
            // Переходов нет: страница одна, ссылки наружу не открываются.
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) = true

            override fun onPageFinished(view: WebView, url: String) {
                loaded = true
                if (pendingLink.isNotEmpty()) view.evaluateJavascript("window.xgwLink && xgwLink()", null)
            }
        }
        web.addJavascriptInterface(Bridge(), "XGW")
        // WebView своих отступов не соблюдает: отступы от системных панелей — у рамки вокруг.
        val frame = FrameLayout(this).apply { addView(web) }
        frame.setOnApplyWindowInsetsListener { view, insets ->
            val bars = insets.getInsets(
                WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout() or WindowInsets.Type.ime()
            )
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsets.CONSUMED
        }
        setContentView(frame)
        // Страница сама отступает от строки состояния и навигации — одинаково на всех Android.
        window.setDecorFitsSystemWindows(false)
        lightBars()
        takeLink(intent)
        web.loadUrl("file:///android_asset/index.html")
        if (Build.VERSION.SDK_INT >= 33) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT) { back() }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeLink(intent)
        if (loaded && pendingLink.isNotEmpty()) web.evaluateJavascript("window.xgwLink && xgwLink()", null)
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        lightBars()
    }

    @Deprecated("startActivityForResult: у Activity без AndroidX другого способа нет")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != ASK_VPN) return
        val id = vpnRequest
        vpnRequest = 0
        if (resultCode == RESULT_OK) {
            startVpn(id)
        } else {
            done(id, JSONObject().put("ok", false).put("error",
                "Android не разрешил VPN. Нажмите «Включить VPN телефона» ещё раз и выберите «ОК»."))
        }
    }

    @Deprecated("Android до 13: системная кнопка «Назад»")
    override fun onBackPressed() = back()

    override fun onDestroy() {
        worker.shutdownNow()
        web.destroy()
        super.onDestroy()
    }

    /** «Назад» сначала закрывает вопрос или подтверждение на странице, потом — приложение. */
    private fun back() {
        web.evaluateJavascript("window.xgwBack ? xgwBack() : false") { handled ->
            if (handled != "true") moveTaskToBack(true)
        }
    }

    private fun lightBars() {
        val night = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
        val light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
        window.insetsController?.setSystemBarsAppearance(if (night) 0 else light, light)
    }

    private fun takeLink(intent: Intent?) {
        val data = intent?.data ?: return
        if (intent.action == Intent.ACTION_VIEW && data.scheme == "xgw") pendingLink = data.toString()
    }

    private fun deviceName(): String =
        Settings.Global.getString(contentResolver, Settings.Global.DEVICE_NAME)?.takeIf { it.isNotBlank() }
            ?: "${Build.MANUFACTURER} ${Build.MODEL}"

    /** Разрешение на VPN есть — служба VPN. */
    private fun startVpn(id: Int) {
        XgwVpn.send(this, XgwVpn.START)
        done(id, JSONObject().put("ok", true))
    }

    /** Разрешение Android на VPN: спросит один раз, дальше prepare() возвращает null. */
    private fun askVpn(id: Int) {
        val consent = VpnService.prepare(this)
        if (consent == null) {
            startVpn(id)
        } else {
            vpnRequest = id
            @Suppress("DEPRECATION")
            startActivityForResult(consent, ASK_VPN)
        }
    }

    /** Спросить о уведомлениях — один раз: отказ запоминает Android, дальше — кнопка в карточке. */
    private fun shouldAskNotes(): Boolean {
        val prefs = getSharedPreferences("xgw", MODE_PRIVATE)
        if (prefs.getBoolean("notes-asked", false)) return false
        prefs.edit().putBoolean("notes-asked", true).apply()
        return true
    }

    private fun notesAllowed(): Boolean = Build.VERSION.SDK_INT < 33 ||
        checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /** Испытание А3: окно уведомлений после окна VPN не появлялось — теперь оно первое, а
     * ответ на него (любой) ведёт к разрешению на VPN. */
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != ASK_NOTES) return
        val id = notesRequest
        notesRequest = 0
        if (id != 0) askVpn(id)
    }

    /** Список серверов для VPN телефона со шлюза: проверить и сохранить; VPN включён — перезапустить Xray. */
    private fun fetchConfig(): JSONObject {
        val binding = keys.binding() ?: return JSONObject().put("ok", false).put("status", 0)
            .put("error", "телефон не привязан")
        val answer = Gateway(binding.url).signed(binding.phone, keys.signer(), "GET", "/api/phone-config", null)
        val out = reply(answer)
        if (answer.status != 200) return out.put("ok", false)
        val problem = try {
            xray.save(out.getJSONObject("body"))
        } catch (exc: Exception) {
            "список серверов не сохранён: ${exc.message ?: exc.javaClass.simpleName}"
        }
        if (problem.isNotEmpty()) return JSONObject().put("ok", false).put("status", 200).put("error", problem)
        if (XgwVpn.state == "on") XgwVpn.send(this, XgwVpn.RELOAD)
        return JSONObject().put("ok", true).put("status", 200).put("servers", xray.info()?.optInt("servers") ?: 0)
    }

    /** Запись трафика устройства со шлюза — в «Загрузки/XGW» (MediaStore: разрешений не нужно). */
    private fun saveRecord(name: String): JSONObject {
        val binding = keys.binding() ?: return JSONObject().put("status", 0).put("error", "телефон не привязан")
        if (!RECORD.matches(name)) return JSONObject().put("status", 0).put("error", "неверное имя записи")
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, "xgw-$name")
            put(MediaStore.Downloads.MIME_TYPE, "application/vnd.tcpdump.pcap")
            put(MediaStore.Downloads.RELATIVE_PATH, "${Environment.DIRECTORY_DOWNLOADS}/XGW")
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: return JSONObject().put("status", 0).put("error", "Android не дал создать файл в «Загрузках»")
        val answer = try {
            // Не дошёл прямой путь посреди файла — запасной пишет его заново («wt»).
            Gateway(binding.url).signed(binding.phone, keys.signer(), "GET", "/api/records/$name", null) { stream ->
                contentResolver.openOutputStream(uri, "wt").use { out -> stream.copyTo(out!!) }
            }
        } catch (exc: Exception) {
            Reply(0, "", exc.message ?: exc.javaClass.simpleName)
        }
        if (answer.status != 200) {
            contentResolver.delete(uri, null, null)
            return reply(answer)
        }
        contentResolver.update(uri, ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }, null, null)
        return JSONObject().put("status", 200).put("ok", true).put("file", "Загрузки/XGW/xgw-$name")
    }

    private fun done(id: Int, result: JSONObject) {
        val text = JSONObject.quote(result.toString())
        runOnUiThread { if (!isDestroyed) web.evaluateJavascript("xgwDone($id, $text)", null) }
    }

    private fun reply(reply: Reply): JSONObject = JSONObject().apply {
        put("status", reply.status)
        if (reply.error.isNotEmpty()) put("error", reply.error)
        val body = try {
            if (reply.body.isEmpty()) JSONObject() else JSONObject(reply.body)
        } catch (exc: Exception) {
            JSONObject().put("error", "шлюз ответил не JSON (HTTP ${reply.status})")
        }
        put("body", body)
    }

    /** Мост для страницы: строки JSON туда и обратно; долгие вызовы — с номером ответа. */
    inner class Bridge {
        @JavascriptInterface
        fun info(): String {
            val binding = keys.binding()
            return JSONObject().apply {
                put("paired", binding != null)
                put("host", binding?.host ?: "")
                put("name", binding?.name ?: "")
                put("device", deviceName())
                put("version", BuildConfig.VERSION_NAME)
                put("dev", BuildConfig.DEV_HTTP)
            }.toString()
        }

        /** Ссылка xgw://pair, с которой открыли приложение (камера, adb), — один раз. */
        @JavascriptInterface
        fun takeLink(): String = pendingLink.also { pendingLink = "" }

        @JavascriptInterface
        fun checkLink(text: String): String = try {
            val link = parsePairLink(text, BuildConfig.DEV_HTTP)
            JSONObject().put("ok", true).put("host", link.host).toString()
        } catch (exc: LinkError) {
            JSONObject().put("ok", false).put("error", exc.message).toString()
        }

        @JavascriptInterface
        fun scan(id: Int) {
            runOnUiThread {
                val options = GmsBarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                    .enableAutoZoom()
                    .build()
                GmsBarcodeScanning.getClient(this@MainActivity, options).startScan()
                    .addOnSuccessListener { code -> done(id, JSONObject().put("ok", true).put("text", code.rawValue ?: "")) }
                    .addOnCanceledListener { done(id, JSONObject().put("ok", false).put("cancel", true)) }
                    .addOnFailureListener { exc ->
                        // Окно сканера — модуль Google Play services: в первый раз он докачивается.
                        val loading = exc is MlKitException && (exc.errorCode == MlKitException.UNAVAILABLE ||
                            (exc.message ?: "").contains("download", ignoreCase = true))
                        done(id, JSONObject().put("ok", false).put("loading", loading)
                            .put("error", exc.message ?: exc.javaClass.simpleName))
                    }
            }
        }

        @JavascriptInterface
        fun pair(text: String, id: Int) {
            worker.execute {
                val result = try {
                    val link = parsePairLink(text, BuildConfig.DEV_HTTP)
                    val answer = Gateway(link.url).pair(link.code, deviceName())
                    val out = reply(answer)
                    if (answer.status == 200) {
                        val body = out.getJSONObject("body")
                        val key = Base64.getDecoder().decode(body.getString("key"))
                        keys.forget()
                        keys.save(link.url, link.host, body.getString("phone"), body.optString("name"), key)
                        body.remove("key")
                    }
                    out
                } catch (exc: LinkError) {
                    JSONObject().put("status", 0).put("error", exc.message)
                } catch (exc: Exception) {
                    JSONObject().put("status", 0).put("error", "привязка не сохранилась: ${exc.message}")
                }
                done(id, result)
            }
        }

        @JavascriptInterface
        fun call(method: String, path: String, body: String, id: Int) {
            worker.execute {
                val binding = keys.binding()
                val result = if (binding == null) {
                    JSONObject().put("status", 0).put("error", "телефон не привязан")
                } else try {
                    reply(Gateway(binding.url).signed(binding.phone, keys.signer(), method, path, body.ifEmpty { null }))
                } catch (exc: Exception) {
                    JSONObject().put("status", 0).put("error", exc.message ?: exc.javaClass.simpleName)
                }
                done(id, result)
            }
        }

        @JavascriptInterface
        fun forget() = keys.forget()

        /** Текст из буфера обмена — для поля «Подписки»: Android отдаёт его только окну в фокусе. */
        @JavascriptInterface
        fun paste(id: Int) = runOnUiThread {
            val clip = getSystemService(ClipboardManager::class.java).primaryClip
            val text = if (clip != null && clip.itemCount > 0) clip.getItemAt(0).coerceToText(this@MainActivity).toString() else ""
            done(id, JSONObject().put("ok", text.isNotBlank()).put("text", text))
        }

        @JavascriptInterface
        fun download(name: String, id: Int) {
            worker.execute { done(id, saveRecord(name)) }
        }

        /** VPN телефона: состояние службы и сохранённого списка серверов. */
        @JavascriptInterface
        fun vpnInfo(): String = XgwVpn.snapshot()
            .put("config", xray.info() ?: JSONObject.NULL)
            .put("notes", notesAllowed() && getSystemService(NotificationManager::class.java).areNotificationsEnabled())
            .put("path", Gateway.path)
            .put("direct_error", Gateway.directError)
            .toString()

        /** Настройки уведомлений XGW: включить скрытое уведомление «VPN XGW». */
        @JavascriptInterface
        fun notesSettings() = runOnUiThread {
            startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
        }

        /** Включить VPN телефона: нет списка серверов — сначала со шлюза, затем разрешение Android. */
        @JavascriptInterface
        fun vpnStart(id: Int) {
            worker.execute {
                if (xray.info() == null) {
                    val fetched = fetchConfig()
                    if (!fetched.optBoolean("ok")) {
                        done(id, fetched)
                        return@execute
                    }
                }
                runOnUiThread {
                    if (notesAllowed() || !shouldAskNotes()) {
                        askVpn(id)
                    } else {
                        notesRequest = id
                        requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), ASK_NOTES)
                    }
                }
            }
        }

        @JavascriptInterface
        fun vpnStop() = XgwVpn.send(this@MainActivity, XgwVpn.STOP)

        @JavascriptInterface
        fun vpnFetch(id: Int) {
            worker.execute { done(id, fetchConfig()) }
        }

        /** Настройки VPN Android: «Постоянная VPN» и «Блокировать соединения без VPN». */
        @JavascriptInterface
        fun vpnSettings() = runOnUiThread { startActivity(Intent(Settings.ACTION_VPN_SETTINGS)) }
    }
}
