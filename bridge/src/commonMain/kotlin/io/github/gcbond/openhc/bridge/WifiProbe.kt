package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.common.MalformedMessageException
import io.github.gcbond.openhc.core.nearby.WifiChannels
import io.github.gcbond.openhc.core.nearby.WifiConnectionInfo
import io.github.gcbond.openhc.core.nearby.WifiMode

/** Synthetic-only probe. Never returns the connection string or credentials. */
internal object WifiProbe {
    fun run() {
        val source = WifiConnectionInfo(WifiMode.HOTSPOT, "192.0.2.2", "stage0\\probe",
            "02:00:00:00:00:01", "synthetic-only", 5745, 5288, "192.0.2.1")
        val encoded = source.encode()
        val parsed = WifiConnectionInfo.parse(encoded)
        check(parsed.mode == WifiMode.HOTSPOT && parsed.hotspotChannel == 149)
        check(parsed.encode() == encoded)
        check(WifiChannels.frequencyOf(149) == 5745)
        check(WifiConnectionInfo.pickPhoneAddress("192.0.2.1") == "192.0.2.2")
        var rejected = false
        try {
            WifiConnectionInfo.parse("invalid")
        } catch (_: MalformedMessageException) {
            rejected = true
        }
        check(rejected)
    }
}
