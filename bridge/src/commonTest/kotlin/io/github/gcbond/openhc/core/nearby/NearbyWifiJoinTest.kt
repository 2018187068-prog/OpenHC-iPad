package io.github.gcbond.openhc.core.nearby

import io.github.gcbond.openhc.bridge.Fe35ControlBridge
import io.github.gcbond.openhc.core.common.ByteReader
import io.github.gcbond.openhc.core.common.ByteWriter
import kotlin.test.*

/** Pinned upstream wire behavior; all credentials/addresses and the authenticated capability
 * supplied by these unit tests are synthetic. Actual crypto-to-owner join is a Simulator gate. */
class NearbyWifiJoinTest {
    private val root = ByteArray(16)
    private val a = ByteArray(16) { (0x10 + it).toByte() }
    private val b = ByteArray(16) { (0x20 + it).toByte() }
    private val network = WifiNetworkConfig(WifiMode.DIRECT, "127.0.0.2", "Synthetic",
        "02:11:22:33:44:55", "synthetic-pass", 2437, "127.0.0.1")
    private val info = network.connectionInfo(41000)
    private fun request(channel: Int = 3, capability: ByteArray = byteArrayOf()) =
        encodeTlv(1, DataChannelMessages.requestValue(channel, capability))
    private fun result(code: Int = 1) = encodeTlv(7, ByteWriter().ea(3).ea(code).toByteArray())
    private fun join() = NearbyWifiJoin(7, 9, 200, 100) { outer, payload ->
        Fe35SessionEvent("SEND_FRAME", frame=NearbyFrame.plain(outer, payload).encode())
    }
    private fun kinds(events: List<Fe35SessionEvent>) = events.map { it.kind }
    private fun payload(event: Fe35SessionEvent): ByteArray {
        val d = NearbyFrameDecoder();d.feed(assertNotNull(event.frame));return assertNotNull(d.next()).payload
    }
    private fun mac() = encodeTlv(2, "02:12:34:56:78:9a".encodeToByteArray())

    @Test fun pendingNetworkUsesOriginalRequestThenOneConfirmationAndMac() {
        val j=join()
        assertEquals(listOf("WIFI_NETWORK_REQUESTED"),kinds(j.resource(request())))
        assertTrue(j.resource(request()).isEmpty())
        val accepted=j.ready(7,9,network,110).single()
        assertContentEquals(DataChannelMessages.acceptPayload(3,1,2437),payload(accepted))
        assertEquals(listOf("WIFI_LISTEN"),kinds(j.resource(result())))
        assertTrue(j.resource(result()).isEmpty())
        assertContentEquals(encodeTlv(1),payload(j.listening(7,9,41000,120).single()))
        val sent=j.wifi(mac())
        assertEquals(listOf("SEND_FRAME","WIFI_WAIT_TCP"),kinds(sent))
        assertContentEquals(encodeTlv(3,info.encode().encodeToByteArray()),payload(sent.first()))
        assertTrue(j.wifi(mac()).isEmpty())
        assertEquals(listOf("TCP_CONTROL_ACCEPTED"),kinds(j.accepted(7,9,150)))
        assertEquals(listOf("WIFI_JOIN_FAILED"),kinds(j.accepted(7,9,151)))
    }
    @Test fun rejectsUnsupportedAndIncompatibleFrequency() {
        val j=join();j.ready(7,9,network,110)
        assertContentEquals(DataChannelMessages.refusePayload(8,DataChannelRefusal.NO_CHANNEL),payload(j.resource(request(8)).single()))
        val no2g=ByteWriter().ea(3).ea(0).toByteArray()
        val rejected=j.resource(request(capability=no2g))
        assertContentEquals(DataChannelMessages.refusePayload(3,DataChannelRefusal.NO_CHANNEL),payload(rejected.first()))
        assertEquals("WIFI_JOIN_FAILED",rejected.last().kind)
    }
    @Test fun resultBeforeAnswerAndUnsolicitedMacDoNotPromote() {
        val j=join()
        assertTrue(j.resource(result()).isEmpty());assertTrue(j.wifi(mac()).isEmpty())
        assertEquals("WIFI_JOIN_FAILED",j.accepted(7,9,110).single().kind)
    }
    @Test fun busyWaitsForRealMacAndActualTcp() {
        val j=join();j.ready(7,9,network,110);j.resource(request());j.resource(result());j.listening(7,9,41000,120)
        assertTrue(j.wifi(encodeTlv(2,"busy".encodeToByteArray())).isEmpty())
        assertEquals("WIFI_JOIN_FAILED",j.accepted(7,9,130).single().kind)
    }
    @Test fun originalExpiryAndClockReversalRevoke() {
        assertEquals("WIFI_JOIN_FAILED",join().tick(200).single().kind)
        val j=join();j.tick(150)
        assertEquals("WIFI_JOIN_FAILED",j.tick(149).single().kind)
        assertEquals("WIFI_JOIN_FAILED",j.ready(7,9,network,151).single().kind)
    }
    @Test fun staleGenerationAndConnectionCallbacksRevoke() {
        assertEquals("WIFI_JOIN_FAILED",join().ready(8,9,network,110).single().kind)
        assertEquals("WIFI_JOIN_FAILED",join().ready(7,10,network,110).single().kind)
    }
    @Test fun stopAndDuplicateReadinessCannotChangeNetwork() {
        val j=join();j.close()
        assertEquals("WIFI_JOIN_FAILED",j.ready(7,9,network,110).single().kind)
        val k=join();k.ready(7,9,network,110)
        assertEquals("WIFI_JOIN_FAILED",k.ready(7,9,network,111).single().kind)
    }
    @Test fun refusalAndMalformedTailNeverStartListener() {
        val j=join();j.ready(7,9,network,110);j.resource(request())
        assertEquals("WIFI_JOIN_FAILED",j.resource(result(255)).single().kind)
        assertFails { join().resource(request()+byteArrayOf(0x81.toByte())) }
        assertFails { join().wifi(encodeTlv(2, "bad-mac".encodeToByteArray())) }
    }
    @Test fun remoteDisconnectReturnsAckThenRevocation() {
        val events=join().wifi(encodeTlv(5))
        assertEquals(listOf("SEND_FRAME","WIFI_JOIN_FAILED"),kinds(events))
        assertContentEquals(encodeTlv(6),payload(events.first()))
    }
    @Test fun exportedBridgeRunsEncryptedFragmentedNegotiationAndGuardsUnauthenticatedRequest() {
        val bridge=Fe35ControlBridge("SYNTHETIC",root,a,b,Fe35RandomSource { ByteArray(it) { 1 } })
        bridge.start(100)
        val handshake=ByteWriter().tlv(1,byteArrayOf(5)).tlv(3,"SYNTHETIC".encodeToByteArray())
            .tlv(5,byteArrayOf(1)).toByteArray()
        bridge.feed(NearbyFrame.plain(0,handshake).encode())
        val cipher=NearbyFrameCipher(root,a,b)
        fun frame(outer:Int,p:ByteArray)=cipher.seal(outer,p,ByteArray(8){2}).encode()
        fun decoded(bytes:ByteArray):ByteArray {
            val d=NearbyFrameDecoder();d.feed(bytes);return cipher.open(assertNotNull(d.next()))
        }
        val denied=bridge.feed(frame(4,request())).single()
        assertContentEquals(DataChannelMessages.refusePayload(3,DataChannelRefusal.BUSY),decoded(assertNotNull(denied.frame)))
        assertTrue(bridge.authenticated(7,9,200,110).isEmpty())
        val events=ArrayList<String>()
        for(byte in frame(4,request())) events+=bridge.feed(byteArrayOf(byte)).map{it.kind}
        assertEquals(listOf("WIFI_NETWORK_REQUESTED"),events)
        val answer=bridge.networkReady(7,9,network,120).single()
        assertContentEquals(DataChannelMessages.acceptPayload(3,1,2437),decoded(assertNotNull(answer.frame)))
        assertEquals("WIFI_LISTEN",bridge.feed(frame(4,result())).single().kind)
        bridge.wifiListening(7,9,41000,130)
        val connection=bridge.feed(frame(33,mac()))
        assertContentEquals(encodeTlv(3,info.encode().encodeToByteArray()),decoded(assertNotNull(connection.first().frame)))
        assertEquals("TCP_CONTROL_ACCEPTED",bridge.tcpAccepted(7,9,140).single().kind)
        assertFalse(connection.toString().contains(info.passphrase))
        bridge.close();cipher.close()
    }
    @Test fun exportedBridgeFailsClosedOnMalformedWifiAndStopsStaleCallbacks() {
        val bridge=Fe35ControlBridge("SYNTHETIC",root,a,b,Fe35RandomSource { ByteArray(it) })
        bridge.start(100)
        bridge.feed(NearbyFrame.plain(0,ByteWriter().tlv(1,byteArrayOf(5)).tlv(3).tlv(5,byteArrayOf(0)).toByteArray()).encode())
        bridge.authenticated(7,9,200,110)
        assertEquals("WIFI_JOIN_FAILED",bridge.feed(NearbyFrame.plain(33,encodeTlv(2,byteArrayOf(0))).encode()).single().kind)
        assertEquals("ERROR_SESSION_CLOSED",bridge.networkReady(7,9,network,120).single().kind)
        bridge.close()
    }
    @Test fun continuingSessionRejectsHandshakeReconfiguration() {
        val bridge=Fe35ControlBridge("SYNTHETIC",root,a,b,Fe35RandomSource { ByteArray(it) })
        bridge.start(100)
        val handshake=NearbyFrame.plain(0,ByteWriter().tlv(1,byteArrayOf(5)).tlv(3)
            .tlv(5,byteArrayOf(0)).toByteArray()).encode()
        bridge.feed(handshake);bridge.authenticated(7,9,200,110)
        assertEquals("WIFI_JOIN_FAILED",bridge.feed(handshake).single().kind)
        assertEquals("ERROR_SESSION_CLOSED",bridge.tcpAccepted(7,9,120).single().kind)
        bridge.close()
    }

    /** Independent OpenSSL AES-128-CFB frames from the actual Python phone driver,
     * with its synthetic zero root, 0x10/0x20 constants and 0xe1 seed. These are
     * fixed wire inputs, not frames generated by the common codec under test. */
    @Test fun actualPhoneDriverConfirmationFragmentsReachListenerAndMacBoundary() {
        fun hex(value: String) = value.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        val requestFrame=hex("7f84818a8188e1e2e3e4e5e6e7e885af2f5cb76c29fc")
        val resultFrame=hex("7f84818a8188e1e2e3e4e5e6e7e884a92e5cb5d0a1")
        val macFrame=hex("7fa1818a8188e1e2e3e4e5e6e7e893ac3def06d63666a58177285e114d1ef603e52d3eac")
        val cipher=NearbyFrameCipher(root,a,b)
        fun decode(bytes: ByteArray): ByteArray {
            val d=NearbyFrameDecoder();d.feed(bytes)
            return cipher.open(assertNotNull(d.next()))
        }
        // Pinned DataChannel command 7 permits the absent optional detail TLV.
        assertContentEquals(byteArrayOf(0x87.toByte(),0x82.toByte(),0x83.toByte(),0x81.toByte()),decode(resultFrame))
        val parsed=DataChannelMessages.parseResult(decode(resultFrame).copyOfRange(2,4))
        assertEquals(3,parsed.dataChannel);assertEquals(1,parsed.result)
        assertNull(parsed.role);assertNull(parsed.frequencyMhz)
        for (split in 1 until resultFrame.size) {
            val bridge=Fe35ControlBridge("SYNTHETIC",root,a,b,Fe35RandomSource { ByteArray(it) { 1 } })
            try {
                bridge.start(100)
                bridge.feed(NearbyFrame.plain(0,ByteWriter().tlv(1,byteArrayOf(5))
                    .tlv(3).tlv(5,byteArrayOf(1)).toByteArray()).encode())
                bridge.authenticated(7,9,200,110)
                bridge.networkReady(7,9,network,120)
                val accepted=ArrayList<io.github.gcbond.openhc.bridge.Fe35ControlBridgeEvent>()
                for (part in requestFrame.toList().chunked(17)) accepted+=bridge.feed(part.toByteArray())
                assertContentEquals(DataChannelMessages.acceptPayload(3,1,2437),decode(assertNotNull(accepted.single().frame)))
                assertTrue(bridge.feed(resultFrame.copyOfRange(0,split)).isEmpty())
                assertEquals(listOf("WIFI_LISTEN"),bridge.feed(resultFrame.copyOfRange(split,resultFrame.size)).map { it.kind })
                assertTrue(bridge.feed(resultFrame).isEmpty(),"duplicate confirmation cannot reopen listener")
                val listening=bridge.wifiListening(7,9,41000,130).single()
                assertContentEquals(encodeTlv(1),decode(assertNotNull(listening.frame)))
                val connection=ArrayList<io.github.gcbond.openhc.bridge.Fe35ControlBridgeEvent>()
                for (part in macFrame.toList().chunked(17)) connection+=bridge.feed(part.toByteArray())
                assertEquals(listOf("SEND_FRAME","WIFI_WAIT_TCP"),connection.map { it.kind })
                assertContentEquals(encodeTlv(3,info.encode().encodeToByteArray()),decode(assertNotNull(connection.first().frame)))
                assertEquals("TCP_CONTROL_ACCEPTED",bridge.tcpAccepted(7,9,140).single().kind)
            } finally { bridge.close() }
        }
        cipher.close()
    }
}
