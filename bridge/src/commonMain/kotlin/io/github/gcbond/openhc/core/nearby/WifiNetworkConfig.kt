package io.github.gcbond.openhc.core.nearby

/** Trusted network readiness, without a claimed TCP listener/port. Validation reuses the pinned
 * connection-info grammar. Credentials never enter toString or diagnostic events. */
class WifiNetworkConfig(mode: WifiMode, phoneIp: String, ssid: String, bssid: String,
    passphrase: String, frequencyMhz: Int, carIp: String) {
    private val validated = WifiConnectionInfo(mode,phoneIp,ssid,bssid,passphrase,frequencyMhz,1,carIp)
    val frequencyMhz: Int get() = validated.frequencyMhz
    val phoneIp: String get() = validated.phoneIp
    val carIp: String get() = validated.carIp
    fun connectionInfo(port: Int) = WifiConnectionInfo(validated.mode,validated.phoneIp,
        validated.ssid,validated.bssid,validated.passphrase,validated.frequencyMhz,port,validated.carIp)
    override fun toString() = "WifiNetworkConfig(configured)"
}
