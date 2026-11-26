package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.common.identity.BluetoothAddress
import io.github.gcbond.openhc.core.common.identity.HostIdentity
import io.github.gcbond.openhc.core.nearby.PairingQrCode
import kotlin.test.*

/** Synthetic inputs only. Source oracle: OpenHC 8132399bea6aa86d68da6d3e1d9e3e001c0a7643. */
class ScanReceiverSessionTest {
    private fun host(name: String = "演示车机") = HostIdentity("A1B2C3", "D4", "Test", name)
    private fun config(lifetime: Long = 1000) = ScanReceiverConfig(host(), "a0-b1-c2-d3-e4-f5", false, lifetime)
    private fun session(lifetime: Long = 1000) = ScanReceiverSession(config(lifetime)) { byteArrayOf(0, 0, 7) }
    private fun kinds(events: List<ScanReceiverEvent>) = events.map { it.kind }
    private fun ready(s: ScanReceiverSession, now: Long = 0): ScanReceiverEvent {
        s.start(now)
        assertTrue(s.onControlRfcommReady(s.generation, 16, now).isEmpty())
        return s.onControlSdpReady(s.generation, now).single()
    }

    @Test fun qrMatchesExactUpstreamOrderUnicodeAndCapabilities() {
        val expected = "hicar://car/connect?devicename=演示车机&mac=A0:B1:C2:D3:E4:F5&moduleid=A1B2C3&submoduleid=D4&pin=000007&ability=4"
        val qr = PairingQrCode.build(host(), "a0-b1-c2-d3-e4-f5", "000007", false)
        assertEquals(expected, qr)
        assertContentEquals(expected.encodeToByteArray(), qr.encodeToByteArray())
        assertEquals(qr, qr.encodeToByteArray().decodeToString())
        assertTrue(PairingQrCode.build(host(), "A0:B1:C2:D3:E4:F5", "000007", true).endsWith("&ability=6"))
        assertEquals("甲_______乙", PairingQrCode.displayName(" 甲&=#%+? 乙 "))
        assertEquals("a_b", PairingQrCode.displayName("a\u0000b"))
    }

    @Test fun invalidConfigQrAndAddressRejectWithoutLeakingInputs() {
        for (address in listOf("02:00:00:00:00:00", "A0:B1-C2:D3:E4:F5", "Ｇ0:B1:C2:D3:E4:F5", "bad")) {
            assertFailsWith<IllegalArgumentException> { ScanReceiverConfig(host(), address, false, 10) }
        }
        for (pin in listOf("12345", "1234567", "１２３４５６", "12345x")) {
            assertFailsWith<IllegalArgumentException> { PairingQrCode.build(host(), "A0:B1:C2:D3:E4:F5", pin, false) }
        }
        assertFailsWith<IllegalArgumentException> { host(" ") }
        assertFailsWith<IllegalArgumentException> { HostIdentity("a1b2c3", "D4", "Test", "Demo") }
        assertFailsWith<IllegalArgumentException> { config(0) }
        assertFailsWith<IllegalArgumentException> { PairingQrCode.displayName(" ") }
        assertContentEquals(byteArrayOf(-96, -79, -62, -45, -28, -11), BluetoothAddress.parse("a0-b1-c2-d3-e4-f5"))
    }

    @Test fun actualRfcommAndSdpRequiredInEitherOrderAndOnlyOnce() {
        val s = session()
        assertTrue(s.onControlSdpReady(0, 0).isEmpty())
        assertTrue(s.onControlAccepted(0, 0).isEmpty())
        assertEquals(listOf("OPEN_CONTROL_LISTENER"), kinds(s.start(10)))
        val generation = s.generation
        assertEquals("STARTING", s.state)
        assertEquals(1010L, s.deadlineMillis)
        assertNull(s.start(11).single().pinCode)
        assertEquals("ALREADY_ACTIVE", s.start(11).single().reason)
        assertTrue(s.onControlSdpReady(generation, 12).isEmpty())
        assertTrue(s.onControlSdpReady(generation, 13).isEmpty())
        val event = s.onControlRfcommReady(generation, 16, 14).single()
        assertEquals("PAIRING_READY", event.kind)
        assertEquals("000007", event.pinCode)
        assertTrue(event.qrCode!!.contains("&pin=000007&"))
        assertEquals("WAITING_FOR_SCAN", s.state)
        assertTrue(s.onControlRfcommReady(generation, 16, 15).isEmpty())
        assertTrue(s.onControlSdpReady(generation, 16).isEmpty())
        assertTrue(s.takeAuthHandoff(generation, 17).isEmpty())
        assertFalse(event.toString().contains("000007"))
        assertFalse(event.toString().contains("A0:B1"))
        assertEquals("ScanReceiverConfig(redacted)", config().toString())
        assertEquals("HostIdentity(redacted)", host().toString())
    }

    @Test fun samePinSurvivesAcceptForOneAuthHandoffButQrIsRevoked() {
        val s = session()
        val shown = ready(s)
        assertEquals(listOf("CLEAR_PAIRING", "CONTROL_CONNECTED"), kinds(s.onControlAccepted(s.generation, 1)))
        assertTrue(s.onControlAccepted(s.generation, 2).isEmpty())
        val handoff = s.takeAuthHandoff(s.generation, 3).single()
        assertEquals("AUTH_HANDOFF", handoff.kind)
        assertEquals(shown.pinCode, handoff.pinCode)
        assertNull(handoff.qrCode)
        assertTrue(s.takeAuthHandoff(s.generation, 4).isEmpty())
        assertEquals(listOf("CLEAR_PAIRING", "CLOSE_CONTROL_TRANSPORT", "STOPPED"), kinds(s.stop(s.generation)))
        assertTrue(s.takeAuthHandoff(s.generation, 5).isEmpty())
        assertTrue(s.stop(s.generation).isEmpty())
        assertNull(s.deadlineMillis)
    }

    @Test fun stopDuringStartupAndStaleEventsAfterRestartCannotReviveQr() {
        val s = session()
        s.start(0)
        val old = s.generation
        assertEquals("CLOSE_CONTROL_TRANSPORT", s.stop(old)[1].kind)
        s.start(5)
        assertTrue(s.generation > old)
        assertTrue(s.onControlRfcommReady(old, 16, 6).isEmpty())
        assertTrue(s.onControlSdpReady(old, 6).isEmpty())
        assertTrue(s.onControlAccepted(old, 6).isEmpty())
        assertTrue(s.onControlFailure(old, 6).isEmpty())
        assertTrue(s.tick(old, 99999).isEmpty())
        assertTrue(s.stop(old).isEmpty())
        assertTrue(s.takeAuthHandoff(old, 6).isEmpty())
        assertEquals("STARTING", s.state)
        s.onControlRfcommReady(s.generation, 16, 6)
        assertEquals("PAIRING_READY", s.onControlSdpReady(s.generation, 7).single().kind)
    }

    @Test fun expiryAtDeadlineCleansStartingWaitingAndConnectedIncludingHandoff() {
        for (stage in 0..2) {
            val s = session(10)
            if (stage == 0) s.start(0) else ready(s)
            if (stage == 2) s.onControlAccepted(s.generation, 1)
            val ended = if (stage == 0) s.onControlSdpReady(s.generation, 10)
                else if (stage == 1) s.tick(s.generation, 10) else s.takeAuthHandoff(s.generation, 10)
            assertEquals(listOf("CLEAR_PAIRING", "CLOSE_CONTROL_TRANSPORT", "STOPPED"), kinds(ended))
            assertEquals("DEADLINE_EXPIRED", ended.last().reason)
            assertTrue(ended.all { it.qrCode == null && it.pinCode == null })
            assertTrue(s.onControlRfcommReady(s.generation, 16, 11).isEmpty())
            assertTrue(s.onControlSdpReady(s.generation, 11).isEmpty())
            assertTrue(s.takeAuthHandoff(s.generation, 11).isEmpty())
        }
    }

    @Test fun failuresAndInvalidOrderingFailClosedWithCleanupOnce() {
        val cases: List<Pair<String, (ScanReceiverSession) -> List<ScanReceiverEvent>>> = listOf(
            "CONTROL_ACCEPT_OUT_OF_ORDER" to { it.onControlAccepted(it.generation, 1) },
            "CONTROL_CHANNEL_INVALID" to { it.onControlRfcommReady(it.generation, 0, 1) },
            "CONTROL_CHANNEL_INVALID" to { it.onControlRfcommReady(it.generation, 31, 1) },
            "CONTROL_READY_CONFLICT" to { it.onControlRfcommReady(it.generation, 16, 1); it.onControlRfcommReady(it.generation, 17, 2) },
            "CONTROL_TRANSPORT_FAILED" to { it.onControlFailure(it.generation, 1) },
            "CLOCK_REVERSED" to { it.tick(it.generation, -1) },
        )
        for ((reason, trigger) in cases) {
            val s = session()
            s.start(0)
            val events = trigger(s)
            assertEquals(listOf("CLEAR_PAIRING", "CLOSE_CONTROL_TRANSPORT", "FAILED"), kinds(events))
            assertEquals(reason, events.last().reason)
            assertTrue(s.onControlFailure(s.generation, 2).isEmpty())
        }
        val s = session()
        ready(s)
        assertEquals("CONTROL_TRANSPORT_FAILED", s.onControlFailure(s.generation, 1).last().reason)
        assertFailsWith<IllegalArgumentException> { session().start(-1) }
        assertFailsWith<IllegalArgumentException> { session().start(Long.MAX_VALUE) }
    }

    @Test fun entropyRejectsUpperTailAndPreservesLeadingZerosAndWipesBuffers() {
        val samples = listOf(byteArrayOf(15, 66, 64), byteArrayOf(15, -1, -1), byteArrayOf(-16, 0, 7))
        var calls = 0
        val pin = ScanPins.next { size -> assertEquals(3, size); samples[calls++] }
        assertEquals(3, calls)
        assertEquals("000007", pin)
        assertTrue(samples.all { it.all { b -> b == 0.toByte() } })
        assertEquals("999999", ScanPins.next { byteArrayOf(15, 66, 63) })
        assertEquals("000000", ScanPins.next { byteArrayOf(0, 0, 0) })
        // Every possible 20-bit outcome has exactly one accepted encoding or is rejected;
        // checking the boundary is deterministic, rather than a flaky statistical RNG test.
        for (value in listOf(0, 1, 9, 10, 99999, 100000, 999999)) {
            assertEquals(value.toString().padStart(6, '0'), ScanPins.next {
                byteArrayOf((value ushr 16).toByte(), (value ushr 8).toByte(), value.toByte())
            })
        }
    }

    @Test fun brokenEntropyIsBoundedRedactedAndDoesNotPublishQr() {
        var calls = 0
        val broken = ScanReceiverSession(config()) { calls++; byteArrayOf(15, -1, -1) }
        val failed = broken.start(0)
        assertEquals(128, calls)
        assertEquals("PIN_ENTROPY_FAILED", failed.last().reason)
        assertTrue(failed.all { it.pinCode == null && it.qrCode == null })
        val wrongSize = byteArrayOf(1, 2)
        val sizeFailure = ScanReceiverSession(config()) { wrongSize }.start(0)
        assertTrue(wrongSize.all { it == 0.toByte() })
        assertEquals("PIN_ENTROPY_FAILED", sizeFailure.last().reason)
        val throwing = ScanReceiverSession(config()) { error("synthetic-sensitive-detail") }.start(0)
        assertFalse(throwing.toString().contains("synthetic-sensitive-detail"))
    }

    @Test fun publicConstructorUsesExistingPlatformSecureEntropy() {
        val s = ScanReceiverSession(config())
        val event = ready(s)
        assertEquals(6, event.pinCode!!.length)
        assertTrue(assertNotNull(event.pinCode).all { it in '0'..'9' })
        s.stop(s.generation)
    }
}
