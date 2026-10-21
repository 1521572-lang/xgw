package net.xgw.android

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
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
    private val worker = Executors.newSingleThreadExecutor()
    @Volatile private var pendingLink = ""
    private var loaded = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        keys = Keys(this)
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
    }
}
