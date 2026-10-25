package net.xgw.android

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Файлы Xray телефона в каталоге приложения: конфиг со шлюза (`/api/phone-config`), его
 * сведения, geoip.dat и geosite.dat из APK и журнал. Конфиг собирает шлюз (src/xgw/generator/phone.py);
 * здесь он только проверяется (`xray run -test`) и хранится: шлюз недоступен — VPN работает
 * на последнем полученном.
 */
class PhoneXray(private val context: Context) {
    val dir = File(context.filesDir, "xray")
    val config = File(dir, "config.json")
    val log = File(dir, "xray.log")
    private val meta = File(dir, "config-meta.json")

    /** Исполняемый файл Xray — из каталога библиотек APK: только оттуда Android разрешает запуск. */
    val exe: String get() = File(context.applicationInfo.nativeLibraryDir, "libxray.so").path

    fun env(): Array<String> = arrayOf(
        "XRAY_TUN_FD=3",
        "XRAY_LOCATION_ASSET=${dir.path}",
        "HOME=${dir.path}",
        "TMPDIR=${context.cacheDir.path}",
    )

    /** Сведения о сохранённом конфиге: время получения, серверы, `outdated` — конфиг старого
     * вида, без входа pult-in; null — конфига нет. */
    fun info(): JSONObject? {
        if (!config.isFile) return null
        val info = try {
            JSONObject(meta.readText())
        } catch (exc: Exception) {
            JSONObject()
        }
        return info.put("outdated", !info.optBoolean("pult"))
    }

    /** geoip.dat и geosite.dat из APK — рядом с конфигом (правила «geoip:private», «geoip:ru»…);
     * копируются заново, когда приложение обновилось. */
    fun prepare() {
        dir.mkdirs()
        val stamp = File(dir, "geo.version")
        val version = BuildConfig.VERSION_CODE.toString()
        val names = listOf("geoip.dat", "geosite.dat")
        if (names.all { File(dir, it).isFile } && stamp.isFile && stamp.readText() == version) return
        for (name in names) {
            val part = File(dir, "$name.new")
            context.assets.open("xray/$name").use { input -> part.outputStream().use { input.copyTo(it) } }
            if (!part.renameTo(File(dir, name))) throw IllegalStateException("$name не сохранён")
        }
        stamp.writeText(version)
    }

    /**
     * Новый конфиг со шлюза: проверить живым Xray и сохранить. Пустая строка — сохранён,
     * иначе — почему нет (прежний конфиг остаётся).
     */
    fun save(body: JSONObject): String {
        prepare()
        val text = body.optJSONObject("config")?.toString() ?: return "шлюз не прислал конфиг"
        val part = File(dir, "config.new.json")
        part.writeText(text)
        val problem = test(part)
        if (problem.isNotEmpty()) {
            part.delete()
            return problem
        }
        if (!part.renameTo(config)) return "конфиг не сохранён"
        val servers = body.optJSONArray("servers")?.length() ?: 0
        meta.writeText(JSONObject().put("time", System.currentTimeMillis()).put("servers", servers)
            .put("gateway", body.optString("version")).put("pult", hasPult(text)).toString())
        return ""
    }

    /** Есть ли в конфиге вход pult-in — запасной путь пульта через VPN телефона (ASSUMPTIONS
     * п. 229). В конфиге, полученном до А3.1, его нет: в испытании А3.1 VPN включился на таком,
     * и пульт по Wi-Fi остался без связи («Failed to connect to /127.0.0.1:17821»). */
    private fun hasPult(text: String): Boolean {
        val inbounds = JSONObject(text).optJSONArray("inbounds") ?: return false
        return (0 until inbounds.length()).any { inbounds.optJSONObject(it)?.optString("tag") == PULT_TAG }
    }

    /** `xray run -test`: дескриптор TUN проверке не нужен — ProcessBuilder годится. */
    private fun test(file: File): String {
        val process = ProcessBuilder(exe, "run", "-test", "-config", file.path)
            .redirectErrorStream(true)
            .also { builder -> env().forEach { item -> item.split("=", limit = 2).let { builder.environment()[it[0]] = it[1] } } }
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        if (!process.waitFor(30, TimeUnit.SECONDS)) {
            process.destroyForcibly()
            return "Xray не проверил конфиг за 30 с"
        }
        if (process.exitValue() == 0) return ""
        val line = output.lines().lastOrNull { it.isNotBlank() } ?: "код ${process.exitValue()}"
        return "Xray не принял конфиг шлюза: ${line.take(300)}"
    }

    /** Последние ошибки из журнала Xray (без времени) — для сообщения человеку; пусто — ошибок нет. */
    fun errors(lines: Int = 2): String = try {
        log.readLines()
            .filter { line -> ERROR_MARKS.any { line.contains(it, ignoreCase = true) } }
            .map { it.replace(STAMP, "").trim() }
            .takeLast(lines).joinToString("; ").take(400)
    } catch (exc: Exception) {
        ""
    }

    private companion object {
        const val PULT_TAG = "pult-in" // generator/phone.py
        val ERROR_MARKS = listOf("[Error]", "panic:", "fatal error", "failed to start")
        val STAMP = Regex("""^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(\.\d+)? """)
    }
}
