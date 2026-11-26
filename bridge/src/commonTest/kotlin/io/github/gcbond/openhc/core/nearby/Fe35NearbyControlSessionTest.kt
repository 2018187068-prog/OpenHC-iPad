package io.github.gcbond.openhc.core.nearby

import io.github.gcbond.openhc.bridge.Fe35ControlBridge
import io.github.gcbond.openhc.core.common.ByteWriter
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Full synthetic frames are from OpenHC 8132399 WirelessSessionTest/TestSupport and RealWirelessFlowTest. */
class Fe35NearbyControlSessionTest {
    private val root = bytes(0x00, 16)
    private val constA = bytes(0x10, 16)
    private val constB = bytes(0x20, 16)
    private val seedA = bytes(0xa1, 8)
    private val seedB = bytes(0xb1, 8)
    private val seedD = bytes(0xd1, 8)
    private val fe36 = hex("0000fe3600001000800000805f9b34fb")

    @Test
    fun publicBridgeRunsSyntheticFramesThroughListenerAndEncryptedResponse() {
        val entropy = arrayListOf(hex("00005ba0"), seedA.copyOf(), seedB.copyOf())
        val bridge = Fe35ControlBridge(DEVICE_ID, root, constA, constB, Fe35RandomSource { size ->
            val next = entropy.removeAt(0)
            check(next.size == size)
            next
        })
        try {
            assertEquals("SEND_FRAME", bridge.start(1_000).single().kind)
            val events = bridge.feed(hex(PHONE_FIRST) + phoneAuthRequestFrame())
            assertEquals(listOf("SEND_FRAME", "HANDSHAKE_COMPLETED", "OPEN_AUTH_LISTENER"), events.map { it.kind })
            assertContentEquals(fe36, events.last().serviceUuid)
            val reply = bridge.listenerReady(4).single()
            assertEquals("SEND_FRAME", reply.kind)
            val decoded = parseFrame(assertNotNull(reply.frame))
            assertTrue(decoded.isEncrypted)
            val payload = NearbyFrameCipher(root, constA, constB).open(decoded)
            val response = SocketMessages.parseResponse(Tlv.parseAll(payload).single().valueView())
            assertEquals(listOf(0, 4, 2, 19, 0), listOf(response.status, response.port, response.channel, response.businessId, response.protocol))
            assertContentEquals(fe36, response.uuid)
        } finally {
            bridge.close()
        }
    }

    @Test
    fun fullUpstreamPhoneFramesReachListenerCallbackAndEncryptedResponse() {
        val cipher = NearbyFrameCipher(root, constA, constB)
        val requestFrame = phoneAuthRequestFrame()
        val session = newSession()

        val initial = session.start(1_000).single()
        assertEquals("SEND_FRAME", initial.kind)
        assertTrue(parseFrame(assertNotNull(initial.frame)).outerType == ChannelManagement.OUTER_TYPE)

        val received = session.feed(hex(PHONE_FIRST) + requestFrame)
        assertEquals(listOf("SEND_FRAME", "HANDSHAKE_COMPLETED", "OPEN_AUTH_LISTENER"), received.map { it.kind })
        assertTrue(session.isHandshakeComplete)
        assertContentEquals(fe36, received.last().serviceUuid)

        val handshakeReply = parseFrame(assertNotNull(received.first().frame))
        assertEquals(ChannelManagement.OUTER_TYPE, handshakeReply.outerType)
        assertTrue(handshakeReply.isEncrypted)
        assertEquals(PAYLOAD_REPLY, cipher.open(handshakeReply).toHex())

        val response = session.onAuthListenerReady(4).single()
        assertEquals("SEND_FRAME", response.kind)
        val replyFrame = parseFrame(assertNotNull(response.frame))
        assertEquals(SocketMessages.OUTER_TYPE_MESSAGE, replyFrame.outerType)
        assertTrue(replyFrame.isEncrypted)
        val replyPayload = cipher.open(replyFrame)
        assertEquals("84a0808482938968696361724175746880900000fe3600001000800000805f9b34fb", replyPayload.toHex())
        val replyTlv = Tlv.parseAll(replyPayload).single()
        assertEquals(SocketMessages.CMD_CREATE_RESPONSE, replyTlv.tag)
        val parsed = SocketMessages.parseResponse(replyTlv.valueView())
        assertEquals(listOf(0, 4, 2, 19, 0), listOf(parsed.status, parsed.port, parsed.channel, parsed.businessId, parsed.protocol))
        assertContentEquals(fe36, parsed.uuid)
        session.close()
    }

    @Test
    fun fragmentedAndCoalescedInputUseTheSameRuntimeAndOutput() {
        val all = hex(PHONE_FIRST) + phoneAuthRequestFrame()
        val coalesced = newSession()
        coalesced.start(0)
        val expected = coalesced.feed(all)

        val fragmented = newSession()
        fragmented.start(0)
        val actual = ArrayList<Fe35SessionEvent>()
        for (byte in all) actual += fragmented.feed(byteArrayOf(byte))

        assertEquals(expected.map { it.kind }, actual.map { it.kind })
        assertContentEquals(expected.first().frame, actual.first().frame)
        assertContentEquals(expected.last().serviceUuid, actual.last().serviceUuid)
        assertEquals(2, SocketMessages.parseRequest(Tlv.parseAll(
            NearbyFrameCipher(root, constA, constB).open(parseFrame(phoneAuthRequestFrame()))).single().valueView()).channel)
    }

    @Test
    fun malformedCrcAndPreHandshakeSocketRequestFollowUpstreamBoundaries() {
        val session = newSession()
        session.start(0)
        val bad = hex(PHONE_FIRST).also { it[it.lastIndex] = (it.last().toInt() xor 1).toByte() }
        assertEquals("INPUT_DISCARDED", session.feed(bad).single().kind)
        assertEquals("INPUT_DISCARDED", session.feed(hex("00")).single().kind)
        val partial = newSession()
        partial.start(0)
        assertTrue(partial.feed(hex("7f808080010084")).isEmpty())
        partial.close()
        assertEquals("INPUT_DISCARDED", session.feed(ByteArray(64 * 1024 + 1)).single().kind)
        assertFalse(session.isHandshakeComplete)

        val cipher = NearbyFrameCipher(root, constA, constB)
        val early = session.feed(phoneAuthRequestFrame())
        assertEquals(listOf("SEND_FRAME", "SOCKET_REQUEST_REJECTED"), early.map { it.kind })
        val rejectedFrame = parseFrame(assertNotNull(early.first().frame))
        assertFalse(rejectedFrame.isEncrypted)
        val response = SocketMessages.parseResponse(Tlv.parseAll(cipher.open(rejectedFrame)).single().valueView())
        assertEquals(listOf(1, 0, 2, 19, 0), listOf(response.status, response.port, response.channel, response.businessId, response.protocol))
        assertNull(response.uuid)

        val timeout = session.onTick(5_000).single()
        assertEquals("HANDSHAKE_TIMED_OUT", timeout.kind)
        assertTrue(session.feed(hex(PHONE_FIRST)).isEmpty())
    }

    @Test
    fun negotiatorMatchesUpstreamDuplicateUuidAndProtocolBitRules() {
        val uuidA = bytes(0x40, 16)
        val uuidB = bytes(0x60, 16)
        fun request(uuid: ByteArray, protocol: Int) = ByteWriter().tlv(3,
            SocketMessages.encodeRequest(SocketMessages.Request(2, 19, "hicarAuth".encodeToByteArray(), protocol, uuid))).toByteArray()

        val machine = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
        val first = machine.onMessageLayerPayload(request(uuidA, 2)).single()
        assertContentEquals(uuidA, assertIs<Fe35ControlNegotiator.Action.OpenAuthListener>(first).uuid)
        assertIs<Fe35ControlNegotiator.Action.Ignored>(machine.onMessageLayerPayload(request(uuidB, 2)).single())
        val replies = machine.onAuthListenerReady(6)
        assertEquals(2, replies.size)
        val firstResponse = SocketMessages.parseResponse(Tlv.parseAll(
            assertIs<Fe35ControlNegotiator.Action.SendControl>(replies[0]).payload).single().valueView())
        val secondResponse = SocketMessages.parseResponse(Tlv.parseAll(
            assertIs<Fe35ControlNegotiator.Action.SendControl>(replies[1]).payload).single().valueView())
        assertEquals(2, firstResponse.protocol)
        assertEquals(2, secondResponse.protocol)
        assertContentEquals(uuidA, firstResponse.uuid)
        assertContentEquals(uuidB, secondResponse.uuid)
    }

    private fun newSession(): Fe35NearbyControlSession {
        val entropy = arrayListOf(hex("00005ba0"), seedA.copyOf(), seedB.copyOf())
        return Fe35NearbyControlSession(DEVICE_ID, root, constA, constB, Fe35RandomSource { size ->
            val next = entropy.removeAt(0)
            check(next.size == size)
            next
        })
    }

    private fun phoneAuthRequestFrame(): ByteArray {
        val request = SocketMessages.encodeRequest(SocketMessages.Request(
            2, 19, "hicarAuth".encodeToByteArray(), 0, null,
        ))
        val payload = ByteWriter().tlv(SocketMessages.CMD_CREATE_REQUEST, request).toByteArray()
        return NearbyFrameCipher(root, constA, constB).seal(
            SocketMessages.OUTER_TYPE_MESSAGE, payload, seedD,
        ).encode()
    }

    private fun parseFrame(bytes: ByteArray): NearbyFrame {
        val decoder = NearbyFrameDecoder()
        decoder.feed(bytes)
        return assertNotNull(decoder.next()).also { assertNull(decoder.next()) }
    }

    private fun bytes(start: Int, size: Int) = ByteArray(size) { (start + it).toByte() }
    private fun hex(text: String) = ByteArray(text.length / 2) { text.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

    private fun ByteArray.toHex(): String = joinToString("") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }

    private companion object {
        const val DEVICE_ID = "CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F"
        const val PAYLOAD_REPLY = "82810284c043443143373346333639433546453042383038303844334430333335454146374439394232414239464531353430334443363231433136364642414443423646868101"
        const val PHONE_FIRST =
            "7f8080801b81818105838d3031323334353637383941420085810290db30313233343536373839414243444546303132" +
            "333435363738394142434445463031323334353637383941424344454630313233343536373839414243444546262630" +
            "26263026264645444342413938373635343332313026263192a7303132333435363738393a3b3c3d3e3f404142434445" +
            "464748494a4b4c4d4e4f50515253545556343b"
    }
}
