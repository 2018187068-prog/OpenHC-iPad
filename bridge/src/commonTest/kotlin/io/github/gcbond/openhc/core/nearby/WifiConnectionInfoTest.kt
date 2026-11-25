package io.github.gcbond.openhc.core.nearby

import io.github.gcbond.openhc.bridge.BridgeSelfCheck
import io.github.gcbond.openhc.core.common.MalformedMessageException
import kotlin.test.*

class WifiConnectionInfoTest {
    private fun fixture(mode: WifiMode = WifiMode.HOTSPOT, frequency: Int = 5745,
        port: Int = 5288, ssid: String = "\"stage0\\network\"", passphrase: String = "synthetic-only",
        phoneIp: String = "192.0.2.2", carIp: String = "192.0.2.1", bssid: String = "02:AA:BB:CC:DD:EE") =
        WifiConnectionInfo(mode, phoneIp, ssid, bssid, passphrase, frequency, port, carIp)

    @Test fun roundTripsBothModesWithoutLoggingConnectionText() {
        for (mode in WifiMode.entries) {
            val source = fixture(mode)
            val parsed = WifiConnectionInfo.parse(source.encode())
            assertEquals(mode, parsed.mode)
            assertEquals("stage0\\network", parsed.ssid)
            assertEquals("02:aa:bb:cc:dd:ee", parsed.bssid)
            assertEquals(if (mode == WifiMode.HOTSPOT) 149 else null, parsed.hotspotChannel)
            assertTrue(parsed.encode() == source.encode(), "roundtrip mismatch")
            assertFalse(source.toString().contains(source.passphrase))
            assertFalse(source.toString().contains(source.ssid))
        }
    }

    @Test fun boundariesAndWireFormat() {
        for (frequency in listOf(2412, 2472, 2484, 5160, 5885)) {
            for (port in listOf(1, 65535)) {
                val source = fixture(frequency = frequency, port = port, ssid = "probe")
                val expected = "192.0.2.2##probe\n02:aa:bb:cc:dd:ee\n" + source.passphrase +
                    "\n$frequency\n1##version:3##$port##${WifiChannels.channelOf(frequency)}##hicarApIp:192.0.2.1"
                assertTrue(source.encode() == expected, "wire mismatch")
                assertEquals(port, WifiConnectionInfo.parse(expected).port)
            }
        }
        for (length in listOf(8, 63, 64)) fixture(passphrase = "a".repeat(length))
        for (length in listOf(0, 7, 65)) {
            assertFailsWith<IllegalArgumentException> { fixture(passphrase = "a".repeat(length)) }
        }
        assertFailsWith<IllegalArgumentException> { fixture(passphrase = "z".repeat(64)) }
        assertFailsWith<IllegalArgumentException> { fixture(passphrase = "synthetic##only") }
        assertFailsWith<IllegalArgumentException> { fixture(passphrase = "synthetic\nonly") }
    }

    @Test fun rejectsInvalidConstructorFields() {
        for (port in listOf(0, -1, 65536)) assertFailsWith<IllegalArgumentException> { fixture(port = port) }
        for (frequency in listOf(2413, 2485, 5155, 5890)) {
            assertFailsWith<IllegalArgumentException> { fixture(frequency = frequency) }
        }
        for (ssid in listOf("", "bad##name", "bad\nname", "bad\u007fname")) {
            assertFailsWith<IllegalArgumentException> { fixture(ssid = ssid) }
        }
        assertFailsWith<IllegalArgumentException> { fixture(phoneIp = "192.0.02.2") }
        assertFailsWith<IllegalArgumentException> { fixture(phoneIp = "192.0.2.1") }
        assertFailsWith<IllegalArgumentException> { fixture(carIp = "256.0.2.1") }
        assertFailsWith<IllegalArgumentException> { fixture(bssid = "not-a-mac") }
    }

    @Test fun rejectsMalformedWireFields() {
        val valid = fixture(ssid = "probe").encode()
        val cases = listOf(
            "", "bad", valid + "##extra",
            valid.replace("version:3", "version:4"),
            valid.replace("\n1##", "\n0##"),
            valid.replace("\n1##", "##"),
            valid.replace("hicarApIp:", "other:"),
            valid.replace("##149##", "##36##"),
            valid.replace("##149##", "##x##"),
            valid.replace("\n5745\n", "\n5746\n"),
            valid.replace("\n5745\n", "\n+5745\n"),
            valid.replace("\n5745\n", "\n1000000000\n"),
            valid.replace("##5288##", "##0##"),
            valid.replace("##5288##", "##65536##"),
            valid.replace("##5288##", "##-1##"),
            valid.replace("##probe\n", "##probe\\bad\n"),
            valid.replace("192.0.2.2", "192.0.02.2"),
        )
        for ((index, text) in cases.withIndex()) {
            assertFailsWith<MalformedMessageException>("malformed case $index") { WifiConnectionInfo.parse(text) }
        }
    }

    @Test fun preservesExistingLeadingZeroNumberBehavior() {
        // Reference decimal() permits leading zeroes. Do not tighten protocol behavior.
        val valid = fixture(ssid = "probe").encode()
        val parsed = WifiConnectionInfo.parse(valid.replace("##5288##", "##05288##"))
        assertEquals(5288, parsed.port)
    }

    @Test fun phoneAddressSelectionAndExhaustion() {
        assertEquals("192.0.2.3", WifiConnectionInfo.pickPhoneAddress("192.0.2.2"))
        assertEquals("192.0.2.4", WifiConnectionInfo.pickPhoneAddress("192.0.2.1", listOf("192.0.2.2", "192.0.2.3")))
        assertFailsWith<IllegalStateException> {
            WifiConnectionInfo.pickPhoneAddress("192.0.2.1", (2..100).map { "192.0.2.$it" })
        }
        assertFailsWith<IllegalArgumentException> { WifiConnectionInfo.pickPhoneAddress("192.0.02.1") }
    }

    @Test fun preservesExceptionMessageAndCause() {
        val cause = IllegalArgumentException("synthetic-cause")
        val failure = MalformedMessageException("synthetic-message", cause)
        assertEquals("synthetic-message", failure.message)
        assertSame(cause, failure.cause)
    }

    @Test fun exportedProbeExecutesParser() {
        assertEquals("WIFI_CONNECTION_INFO_OK", BridgeSelfCheck().wifiConnectionInfoSelfCheck())
    }
}
