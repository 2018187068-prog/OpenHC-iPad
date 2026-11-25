package io.github.gcbond.openhc.bridge

class BridgeSelfCheck {
    fun selfCheck(): String = "KOTLIN_BRIDGE_OK"

    fun wifiConnectionInfoSelfCheck(): String = try {
        WifiProbe.run()
        "WIFI_CONNECTION_INFO_OK"
    } catch (_: Exception) {
        "WIFI_CONNECTION_INFO_FAILED"
    }
}
