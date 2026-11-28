plugins {
    kotlin("multiplatform")
}

kotlin {
    jvm()
    iosArm64()
    iosSimulatorArm64()

    targets.withType<org.jetbrains.kotlin.gradle.plugin.mpp.KotlinNativeTarget>().configureEach {
        val cryptoTargetName = name
        compilations.getByName("main").cinterops.create("openhcCrypto") {
            definitionFile.set(project.file("src/nativeInterop/cinterop/openhc_crypto.def"))
            includeDirs(rootProject.file("native/crypto"))
            includeDirs(rootProject.file("native/dmsdp"))
            extraOpts("-libraryPath", rootProject.file("artifacts/crypto/$cryptoTargetName").absolutePath)
        }
        binaries.framework {
            baseName = "OpenHCBridge"
            isStatic = true
        }
    }

    sourceSets {
        commonMain.dependencies {
            // Exact version used by reference 8132399; common JSON DOM only,
            // no compiler plugin or new crypto implementation.
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1")
        }
        jvmMain.dependencies {
            implementation("org.bouncycastle:bcprov-jdk18on:1.79")
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
        }
    }
}
