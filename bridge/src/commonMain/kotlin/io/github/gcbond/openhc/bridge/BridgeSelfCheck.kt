package io.github.gcbond.openhc.bridge

class BridgeSelfCheck {
    fun authSelfCheck(): String = io.github.gcbond.openhc.bridge.auth.AuthProbe.run()
    fun selfCheck(): String = "KOTLIN_BRIDGE_OK"

    fun wifiConnectionInfoSelfCheck(): String = try {
        WifiProbe.run()
        "WIFI_CONNECTION_INFO_OK"
    } catch (_: Exception) {
        "WIFI_CONNECTION_INFO_FAILED"
    }
}
