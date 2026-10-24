import com.android.build.api.variant.ApplicationAndroidComponentsExtension
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.security.MessageDigest
import java.util.zip.ZipFile

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Xray для VPN телефона (А3) — официальные архивы выпуска той же версии, что на шлюзе
// (26.10.21, ASSUMPTIONS п. 226), скачанные с согласия заказчика. В репозитории их нет:
// каталог задаётся свойством xgw.xrayDir (по умолчанию — как на машине разработки), сборка
// сверяет SHA-256 и берёт из архива xray (→ libxray.so), geoip.dat и geosite.dat.
val xrayDir = providers.gradleProperty("xgw.xrayDir").getOrElse("C:/toolchain/xray/26.10.21")
val xrayArchives = mapOf(
    "arm64-v8a" to ("Xray-android-arm64-v8a" to "d81604f35a56c98ea6091142c1c744f4895c7384bc2e1c85cd910612c70794e9"),
    "x86_64" to ("Xray-android-amd64" to "58546b1a2711164dc0db9b847fca3d3d6829b2631ab8d6105dc6790a26c80934"),
)

/** Распаковка Xray из архива: проверка SHA-256, затем xray → <abi>/libxray.so или файлы geo*.dat. */
abstract class UnpackXray : DefaultTask() {
    @get:Input abstract val root: Property<String>
    @get:Input abstract val archives: MapProperty<String, String>
    @get:Input abstract val digests: MapProperty<String, String>
    @get:Input abstract val assetsOnly: Property<Boolean>
    @get:OutputDirectory abstract val outputDir: DirectoryProperty

    @TaskAction
    fun unpack() {
        val out = outputDir.get().asFile
        out.deleteRecursively()
        for ((abi, name) in archives.get()) {
            val zip = File(root.get(), "$name/$name.zip")
            if (!zip.isFile) throw GradleException("нет архива Xray $zip (свойство xgw.xrayDir)")
            val digest = MessageDigest.getInstance("SHA-256").digest(zip.readBytes())
                .joinToString("") { "%02x".format(it) }
            if (digest != digests.get()[abi]) throw GradleException("SHA-256 архива $zip не совпал")
            val wanted = if (assetsOnly.get()) {
                listOf("geoip.dat", "geosite.dat").associateWith { File(out, "xray/$it") }
            } else {
                mapOf("xray" to File(out, "$abi/libxray.so"))
            }
            ZipFile(zip).use { archive ->
                for ((entry, target) in wanted) {
                    target.parentFile.mkdirs()
                    archive.getInputStream(archive.getEntry(entry)).use { input ->
                        target.outputStream().use { input.copyTo(it) }
                    }
                }
            }
            if (assetsOnly.get()) break
        }
    }
}

val unpackXrayLibs = tasks.register<UnpackXray>("unpackXrayLibs") {
    root.set(xrayDir)
    archives.set(xrayArchives.mapValues { it.value.first })
    digests.set(xrayArchives.mapValues { it.value.second })
    assetsOnly.set(false)
    outputDir.set(layout.buildDirectory.dir("generated/xray/jniLibs"))
}
val unpackXrayAssets = tasks.register<UnpackXray>("unpackXrayAssets") {
    root.set(xrayDir)
    archives.set(xrayArchives.mapValues { it.value.first })
    digests.set(xrayArchives.mapValues { it.value.second })
    assetsOnly.set(true)
    outputDir.set(layout.buildDirectory.dir("generated/xray/assets"))
}

android {
    namespace = "net.xgw.android"
    compileSdk = 36
    ndkVersion = "28.2.13676358"
    defaultConfig {
        applicationId = "net.xgw.android"
        minSdk = 30
        targetSdk = 36
        versionCode = 6
        versionName = "0.1.17-a3"
    }
    buildTypes {
        getByName("debug") {
            // Только для эмулятора: шлюз-демо по http://10.0.2.2 (tests/panel_demo.py --app-port).
            buildConfigField("boolean", "DEV_HTTP", "true")
            applicationIdSuffix = ".dev"
            ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        }
        getByName("release") {
            buildConfigField("boolean", "DEV_HTTP", "false")
            isMinifyEnabled = false
            // Одна подпись у всех сборок с этой машины: новый APK ставится поверх прежнего.
            signingConfig = signingConfigs.getByName("debug")
            // Телефон заказчика — Galaxy S25 Ultra (arm64); x86_64 — только эмулятору.
            ndk { abiFilters += listOf("arm64-v8a") }
        }
    }
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    packaging {
        // Xray запускается файлом из каталога библиотек: он должен лежать там распакованным.
        jniLibs { useLegacyPackaging = true }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        buildConfig = true
    }
}

extensions.getByType(ApplicationAndroidComponentsExtension::class.java).onVariants { variant ->
    variant.sources.jniLibs?.addGeneratedSourceDirectory(unpackXrayLibs, UnpackXray::outputDir)
    variant.sources.assets?.addGeneratedSourceDirectory(unpackXrayAssets, UnpackXray::outputDir)
}

kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.JVM_17
    }
}

dependencies {
    // Сканер QR из Google Play services: окно камеры даёт система, разрешения на камеру
    // приложению не нужно (решение заказчика 20.10.2026).
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
}
