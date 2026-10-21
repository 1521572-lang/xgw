import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "net.xgw.android"
    compileSdk = 36
    defaultConfig {
        applicationId = "net.xgw.android"
        minSdk = 30
        targetSdk = 36
        versionCode = 2
        versionName = "0.1.17-a2"
    }
    buildTypes {
        getByName("debug") {
            // Только для эмулятора: шлюз-демо по http://10.0.2.2 (tests/panel_demo.py --app-port).
            buildConfigField("boolean", "DEV_HTTP", "true")
            applicationIdSuffix = ".dev"
        }
        getByName("release") {
            buildConfigField("boolean", "DEV_HTTP", "false")
            isMinifyEnabled = false
            // Одна подпись у всех сборок с этой машины: новый APK ставится поверх прежнего.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        buildConfig = true
    }
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
