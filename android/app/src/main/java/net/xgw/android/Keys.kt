package net.xgw.android

import android.content.Context
import android.security.keystore.KeyProperties
import android.security.keystore.KeyProtection
import java.security.KeyStore
import javax.crypto.Mac
import javax.crypto.SecretKey
import javax.crypto.spec.SecretKeySpec

/**
 * Привязка телефона: ключ HMAC-SHA256 — в Android Keystore (прочитать нельзя, только
 * подписывать), адрес шлюза и id телефона — в настройках приложения. Резервные копии их не
 * берут (allowBackup = false, data_extraction_rules.xml).
 */
class Keys(context: Context) {
    companion object {
        private const val ALIAS = "xgw-phone"
        private const val PROVIDER = "AndroidKeyStore"
    }

    data class Binding(val url: String, val host: String, val phone: String, val name: String)

    private val prefs = context.getSharedPreferences("xgw", Context.MODE_PRIVATE)

    private fun store(): KeyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }

    fun binding(): Binding? {
        val url = prefs.getString("url", null) ?: return null
        val phone = prefs.getString("phone", null) ?: return null
        if (!store().containsAlias(ALIAS)) return null
        return Binding(url, prefs.getString("host", "") ?: "", phone, prefs.getString("name", "") ?: "")
    }

    /** Ключ из ответа /api/pair уходит в Keystore, копия в памяти стирается. */
    fun save(url: String, host: String, phone: String, name: String, key: ByteArray) {
        try {
            val entry = KeyStore.SecretKeyEntry(SecretKeySpec(key, KeyProperties.KEY_ALGORITHM_HMAC_SHA256))
            store().setEntry(ALIAS, entry, KeyProtection.Builder(KeyProperties.PURPOSE_SIGN).build())
        } finally {
            key.fill(0)
        }
        prefs.edit().putString("url", url).putString("host", host).putString("phone", phone)
            .putString("name", name).commit()
    }

    fun signer(): Signer {
        val key = store().getKey(ALIAS, null) as SecretKey
        return Signer { data ->
            Mac.getInstance(KeyProperties.KEY_ALGORITHM_HMAC_SHA256).run {
                init(key)
                doFinal(data)
            }
        }
    }

    fun forget() {
        prefs.edit().clear().commit()
        store().let { if (it.containsAlias(ALIAS)) it.deleteEntry(ALIAS) }
    }
}
