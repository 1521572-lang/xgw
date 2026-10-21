package net.xgw.android

import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.net.URLDecoder
import java.security.MessageDigest
import java.security.SecureRandom
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Base64

/**
 * Связь со шлюзом XGW через Tailscale Funnel: https://<шлюз>.<tailnet>.ts.net/ (API приложения,
 * src/xgw/watch/appapi.py). Ключ телефона здесь не виден — подписывает [Signer] (Keystore).
 */

/** Ссылка из QR-кода панели: xgw://pair?u=https://<шлюз>.<tailnet>.ts.net&c=<код>. */
data class PairLink(val url: String, val host: String, val code: String)

class LinkError(message: String) : Exception(message)

private val CODE = Regex("[A-Za-z0-9_-]{16,64}")
private val LABEL = Regex("[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")

fun parsePairLink(text: String, devHttp: Boolean = false): PairLink {
    val link = text.trim()
    val prefix = "xgw://pair?"
    if (!link.startsWith(prefix)) {
        throw LinkError("Это не QR-код XGW: наведите камеру на код из карточки «Телефоны» в панели")
    }
    val query = link.removePrefix(prefix).split("&").mapNotNull { part ->
        val at = part.indexOf('=')
        if (at <= 0) null else part.substring(0, at) to URLDecoder.decode(part.substring(at + 1), "UTF-8")
    }.toMap()
    val code = query["c"] ?: ""
    if (!CODE.matches(code)) throw LinkError("В QR-коде нет кода привязки")
    val url = gatewayUrl(query["u"] ?: "", devHttp)
    return PairLink(url, URI(url).host, code)
}

/** Адрес шлюза: только https://<имя>.ts.net без пути и порта (Funnel на 443). */
fun gatewayUrl(text: String, devHttp: Boolean = false): String {
    val uri = try {
        URI(text.trim().trimEnd('/'))
    } catch (exc: Exception) {
        throw LinkError("Неверный адрес шлюза в QR-коде")
    }
    val host = (uri.host ?: "").lowercase()
    val plain = uri.rawPath.isNullOrEmpty() && uri.rawQuery == null && uri.rawFragment == null &&
        uri.rawUserInfo == null
    if (devHttp && uri.scheme == "http" && host == "10.0.2.2" && plain) {
        return "http://10.0.2.2:${uri.port}"
    }
    val labels = host.split(".")
    if (uri.scheme != "https" || !plain || (uri.port != -1 && uri.port != 443) ||
        !host.endsWith(".ts.net") || labels.size < 4 || !labels.all { LABEL.matches(it) }
    ) {
        throw LinkError("Адрес шлюза в QR-коде — не Tailscale Funnel (https://<шлюз>.<tailnet>.ts.net)")
    }
    return "https://$host"
}

/** Что подписывает телефон — как phones.signed_text на шлюзе. */
fun signedText(phone: String, method: String, path: String, stamp: String, nonce: String, body: ByteArray): ByteArray {
    val digest = MessageDigest.getInstance("SHA-256").digest(body).joinToString("") { "%02x".format(it) }
    return listOf(phone, method.uppercase(), path, stamp, nonce, digest).joinToString("\n").toByteArray(Charsets.UTF_8)
}

fun interface Signer {
    fun sign(data: ByteArray): ByteArray
}

class Reply(val status: Int, val body: String, val error: String = "")

class Gateway(private val url: String) {
    companion object {
        const val TIMEOUT_MS = 20_000
        private val random = SecureRandom()

        /** Насколько часы шлюза впереди часов телефона, мс (из заголовка Date ответов):
         * подпись принимается при расхождении не больше минуты, а часы телефона могут уйти. */
        @Volatile var skewMs = 0L
    }

    fun hello(): Reply = send("GET", "/api/hello", ByteArray(0), emptyMap())

    fun pair(code: String, name: String): Reply {
        val body = org.json.JSONObject().put("code", code).put("name", name).toString()
        return send("POST", "/api/pair", body.toByteArray(Charsets.UTF_8), emptyMap())
    }

    fun signed(phone: String, signer: Signer, method: String, path: String, body: String?): Reply {
        val data = (body ?: "").toByteArray(Charsets.UTF_8)
        val stamp = ((System.currentTimeMillis() + skewMs) / 1000).toString()
        val nonce = ByteArray(18).also { random.nextBytes(it) }
            .let { Base64.getUrlEncoder().withoutPadding().encodeToString(it) }
        val signature = signer.sign(signedText(phone, method, path, stamp, nonce, data))
            .joinToString("") { "%02x".format(it) }
        return send(method, path, data, mapOf(
            "X-XGW-Phone" to phone, "X-XGW-Time" to stamp, "X-XGW-Nonce" to nonce,
            "X-XGW-Signature" to signature,
        ))
    }

    private fun send(method: String, path: String, body: ByteArray, headers: Map<String, String>): Reply {
        val connection = URL(url + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = TIMEOUT_MS
            connection.readTimeout = TIMEOUT_MS
            connection.instanceFollowRedirects = false
            connection.useCaches = false
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("Accept", "application/json")
            headers.forEach { (name, value) -> connection.setRequestProperty(name, value) }
            if (method == "POST") {
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(body.size)
                connection.outputStream.use { it.write(body) }
            }
            val status = connection.responseCode
            noteDate(connection.getHeaderField("Date"))
            val stream = if (status >= 400) connection.errorStream else connection.inputStream
            val text = stream?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
            Reply(status, text)
        } catch (exc: IOException) {
            Reply(0, "", exc.message ?: exc.javaClass.simpleName)
        } finally {
            connection.disconnect()
        }
    }

    private fun noteDate(header: String?) {
        if (header == null) return
        val server = try {
            ZonedDateTime.parse(header, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant().toEpochMilli()
        } catch (exc: Exception) {
            return
        }
        val skew = server - System.currentTimeMillis()
        // Date — с точностью до секунды: меньшие расхождения не трогаем.
        skewMs = if (kotlin.math.abs(skew) > 5_000) skew else 0L
    }
}
