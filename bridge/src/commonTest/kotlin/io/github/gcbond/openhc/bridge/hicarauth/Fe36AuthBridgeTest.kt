package io.github.gcbond.openhc.bridge.hicarauth

import io.github.gcbond.openhc.bridge.*
import io.github.gcbond.openhc.bridge.hicarauth.hichain.*
import io.github.gcbond.openhc.core.common.identity.HostIdentity
import kotlin.test.*

class Fe36AuthBridgeTest {
    private val config = Fe36AuthConfig(Synthetic.SERVICE, Synthetic.CAR_ID, Synthetic.ENVELOPE_VERSION,
        linkedMapOf("model" to "SYNTHETIC", "brand" to "TEST"))
    private fun handshake(pin: Boolean = true, usb: Boolean = false, id: String = Synthetic.PHONE_ID) =
        phoneEnvelope(1, "{\"deviceId\":\"$id\",\"has_pin\":$pin,\"usb_connection\":$usb}").encodeToByteArray()

    private fun scanHandoff(fixedTestPin: String? = null): Pair<ScanReceiverEvent, String> {
        val config = ScanReceiverConfig(HostIdentity("A1B2C3", "D4", "Synthetic", "Synthetic"),
            "A0:B1:C2:D3:E4:F5", false, 20000)
        val scan = if (fixedTestPin == null) ScanReceiverSession(config) else ScanReceiverSession(config) {
            val n = fixedTestPin.toInt()
            byteArrayOf((n ushr 16).toByte(), (n ushr 8).toByte(), n.toByte())
        }
        scan.start(0)
        assertTrue(scan.onControlRfcommReady(1, 16, 1).isEmpty())
        val published = scan.onControlSdpReady(1, 2).single()
        assertEquals("PAIRING_READY", published.kind)
        assertEquals("CLEAR_PAIRING", scan.onControlAccepted(1, 3).first().kind)
        val handoff = scan.takeAuthHandoff(1, 4).single()
        assertEquals(published.pinCode, handoff.pinCode)
        assertTrue(scan.takeAuthHandoff(1, 5).isEmpty())
        return handoff to checkNotNull(published.pinCode)
    }
    private fun bridge(store: TrustStore = InMemoryTrustStore(), h: ScanReceiverEvent = scanHandoff().first): Fe36AuthSessionBridge {
        val bridge = Fe36AuthSessionBridge(config, store)
        assertEquals(listOf("OPEN_AUTH_CONNECTION"), bridge.handoff(h, 10, 20000).map { it.kind })
        assertTrue(bridge.connected(h.generation, 7, 11).isEmpty())
        return bridge
    }
    private fun feed(b: Fe36AuthSessionBridge, bytes: ByteArray, fragment: Int = 3): List<Fe36AuthAction> {
        val output = ArrayList<Fe36AuthAction>()
        for (offset in bytes.indices step fragment)
            output += b.receive(1, 7, bytes.copyOfRange(offset, minOf(bytes.size, offset + fragment)), 12)
        return output
    }
    private fun converse(b: Fe36AuthSessionBridge, phone: TestPhone): List<Fe36AuthAction> {
        var next: String? = phone.startPake()
        val actions = ArrayList<Fe36AuthAction>()
        repeat(8) {
            val message = next ?: return actions
            next = null
            val step = feed(b, phoneEnvelope(3, message).encodeToByteArray())
            actions += step
            for (send in step.filter { it.kind == "SEND" }) {
                val outer = parseJsonObject(checkNotNull(send.bytes).decodeToString(), "test")
                phone.onMessage(checkNotNull(outer.exactString("data")))?.let { next = it }
            }
        }
        error("AUTH_TEST_EXCHANGE_LIMIT")
    }
    @Test fun sameScanPinFullRealCryptoExchangeAndOneShotKey() {
        val (handoff, pin) = scanHandoff()
        val trust = InMemoryTrustStore()
        val b = bridge(trust, handoff)
        assertTrue(feed(b, handshake(), 1).any { it.kind == "SEND" })
        val phone = TestPhone(Synthetic.SERVICE, Synthetic.PHONE_ID, Synthetic.CAR_ID, pin, PlatformAuthRandom)
        val actions = converse(b, phone)
        assertTrue(phone.succeeded)
        assertEquals(1, actions.count { it.kind == "AUTHENTICATED" })
        assertEquals("SEND", actions[actions.indexOfFirst { it.kind == "AUTHENTICATED" } - 1].kind)
        assertContentEquals(phone.sessionKey, b.takeSessionKey(1, 7, 13))
        assertNull(b.takeSessionKey(1, 7, 13))
        assertEquals(1, trust.snapshot().peers.size)
        assertTrue(b.handoff(handoff, 13, 20000).isEmpty())
        assertTrue(b.receive(1, 7, byteArrayOf(123), 14).isEmpty())
        assertTrue(actions.none { it.toString().contains(pin) || it.toString().contains(Synthetic.PHONE_ID) })
    }
    @Test fun wrongPinNeverCommitsOrAuthenticates() {
        val (h, pin) = scanHandoff(); val trust = InMemoryTrustStore(); val b = bridge(trust, h)
        feed(b, handshake())
        val wrong = if (pin == "000000") "000001" else "000000"
        val actions = converse(b, TestPhone(Synthetic.SERVICE, Synthetic.PHONE_ID, Synthetic.CAR_ID, wrong, PlatformAuthRandom))
        assertTrue(actions.none { it.kind == "AUTHENTICATED" })
        assertEquals(listOf("FAILED", "CLOSE"), actions.takeLast(2).map { it.kind })
        assertTrue(trust.snapshot().peers.isEmpty())
        assertNull(b.takeSessionKey(1, 7, 13))
    }
    @Test fun verifiedKeyIsRevokedBeforeConsumptionByEveryTerminalBoundary() {
        for (terminal in listOf("stop", "disconnect", "expiry", "reversed", "takeExpired", "takeReversed")) {
            val (h, pin) = scanHandoff(); val b = bridge(h = h)
            feed(b, handshake())
            val phone = TestPhone(Synthetic.SERVICE, Synthetic.PHONE_ID, Synthetic.CAR_ID, pin, PlatformAuthRandom)
            assertEquals(1, converse(b, phone).count { it.kind == "AUTHENTICATED" })
            assertNull(b.takeSessionKey(2, 7, 13))
            assertNull(b.takeSessionKey(1, 8, 13))
            val actions = when (terminal) {
                "stop" -> b.stop(1)
                "disconnect" -> b.disconnected(1, 7)
                "expiry" -> b.tick(1, 20000)
                "reversed" -> b.tick(1, 9)
                "takeExpired" -> { assertNull(b.takeSessionKey(1, 7, 20000)); emptyList() }
                else -> { assertNull(b.takeSessionKey(1, 7, 9)); emptyList() }
            }
            if (!terminal.startsWith("take")) assertEquals(listOf("CLOSE"), actions.map { it.kind }, terminal)
            assertNull(b.takeSessionKey(1, 7, 20001), terminal)
            assertTrue(b.stop(1).isEmpty(), terminal)
        }
    }
    @Test fun recordedValidTranscriptCannotAuthenticateFreshSession() {
        // Independent C phone goldens, not a response computed from this session.
        val trust = InMemoryTrustStore(); val b = bridge(trust, scanHandoff(Synthetic.PIN).first)
        feed(b, handshake())
        val actions = Vectors.phoneMessages("pair").flatMap { feed(b, phoneEnvelope(3, it).encodeToByteArray()) }
        assertTrue(actions.none { it.kind == "AUTHENTICATED" })
        assertEquals(listOf("FAILED", "CLOSE"), actions.takeLast(2).map { it.kind })
        assertTrue(trust.snapshot().peers.isEmpty())
        assertNull(b.takeSessionKey(1, 7, 13))
    }
    @Test fun signedExchangeIdentityMustMatchHandshakeBeforeTrustCommit() {
        val (h, pin) = scanHandoff(); val trust = InMemoryTrustStore(); val b = bridge(trust, h)
        feed(b, handshake())
        val phone = TestPhone(Synthetic.SERVICE, "OTHER_SYNTHETIC_PEER", Synthetic.CAR_ID, pin, PlatformAuthRandom)
        val actions = converse(b, phone)
        assertTrue(actions.none { it.kind == "AUTHENTICATED" })
        assertEquals(listOf("FAILED", "CLOSE"), actions.takeLast(2).map { it.kind })
        assertTrue(trust.snapshot().peers.isEmpty() && trust.snapshot().identities.isEmpty())
        assertNull(b.takeSessionKey(1, 7, 13))
    }
    @Test fun unsignedReconnectAndConnectionModeAreRejected() {
        for (request in listOf(handshake(pin = false), handshake(usb = true))) {
            val b = bridge()
            assertEquals(listOf("FAILED", "CLOSE"), feed(b, request).takeLast(2).map { it.kind })
        }
    }
    @Test fun handshakeRetriesBeforeAuthAreBoundedAndPeerCannotChange() {
        val b = bridge()
        repeat(3) { assertEquals(listOf("SEND"), feed(b, handshake()).map { a -> a.kind }) }
        assertEquals("FAILED", feed(b, handshake()).first().kind)
        val changed = bridge(); feed(changed, handshake())
        assertEquals("FAILED", feed(changed, handshake(id = "OTHER_SYNTHETIC_PEER")).first().kind)
        val late = bridge(); feed(late, handshake())
        feed(late, phoneEnvelope(3, TestPhone(Synthetic.SERVICE, Synthetic.PHONE_ID, Synthetic.CAR_ID, "123456", PlatformAuthRandom).startPake()).encodeToByteArray())
        assertEquals("FAILED", feed(late, handshake()).first().kind)
    }
    @Test fun cancellationDeadlineClockAndConnectionFence() {
        val stale = bridge()
        assertTrue(stale.receive(2, 7, handshake(), 12).isEmpty())
        assertTrue(stale.disconnected(1, 8).isEmpty())
        assertEquals("FAILED", stale.receive(1, 8, handshake(), 12).first().kind)
        val duplicate = bridge()
        assertEquals("FAILED", duplicate.connected(1, 7, 12).first().kind)
        val deadline = bridge()
        assertEquals("DEADLINE_EXPIRED", deadline.tick(1, 20000).first().reason)
        val reverse = bridge()
        assertEquals("CLOCK_REVERSED", reverse.tick(1, 9).first().reason)
        val stop = bridge(); feed(stop, byteArrayOf(123))
        assertEquals(listOf("FAILED", "CLOSE"), stop.stop(1).map { it.kind })
        assertTrue(stop.stop(1).isEmpty()); assertTrue(stop.receive(1, 7, handshake(), 12).isEmpty())
        assertEquals("DISCONNECTED", bridge().disconnected(1, 7).first().reason)
    }
    @Test fun malformedUtf8DepthSizeAndFramingFailClosed() {
        val malformed = listOf(byteArrayOf(123, 34, 0xc0.toByte(), 0xaf.toByte(), 34, 58, 49, 125),
            "[]".encodeToByteArray(), "{\"oper_type\":1,\"data\":false}".encodeToByteArray(),
            ("{".repeat(34)).encodeToByteArray(), ByteArray(4097) { 32 })
        for (payload in malformed) {
            val b = bridge()
            val result = if (payload.size > 4096) b.receive(1, 7, payload, 12) else feed(b, payload)
            assertTrue(result.any { it.kind == "FAILED" })
            assertNull(b.takeSessionKey(1, 7, 13))
        }
        val limits = bridge()
        var last = emptyList<Fe36AuthAction>()
        repeat(17) { last = limits.receive(1, 7, ByteArray(4096) { 32 }, 12) }
        assertEquals("AUTH_INPUT_LIMIT", last.first().reason)
    }
    @Test fun pinGeneratorRejectsBiasAndRetainsLeadingZeros() {
        val zeros = object : AuthRandom { override fun nextBytes(bytes: ByteArray) { bytes.fill(0) } }
        assertEquals("000000", PinCodes.random(zeros))
        val fail = object : AuthRandom { override fun nextBytes(bytes: ByteArray) { bytes.fill(255.toByte()) } }
        assertFails { PinCodes.random(fail) }
    }
    @Test fun versionUnsignedPortMatchesStrtoulBoundarySemantics() {
        assertEquals("4294967295.0.0", KeyAgreementVersion.parse("-1").toString())
        assertEquals("4294967295.0.0", KeyAgreementVersion.parse("18446744073709551616").toString())
        assertEquals("0.0.0", KeyAgreementVersion.parse("4294967296").toString())
        assertEquals("1.0.0", KeyAgreementVersion.parse("  +1x").toString())
    }
}
