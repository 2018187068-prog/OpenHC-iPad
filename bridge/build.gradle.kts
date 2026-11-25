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
            extraOpts("-libraryPath", rootProject.file("artifacts/crypto/$cryptoTargetName").absolutePath)
        }
        binaries.framework {
            baseName = "OpenHCBridge"
            isStatic = true
        }
    }

    sourceSets {
        commonMain.dependencies {}
        jvmMain.dependencies {
            implementation("org.bouncycastle:bcprov-jdk18on:1.79")
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
        }
    }
}
