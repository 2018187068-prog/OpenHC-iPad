package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.common.ByteWriter
import io.github.gcbond.openhc.core.nearby.*
import kotlin.test.*

class NearbyTcpControlBridgeTest {
    private val root = ByteArray(16)
    private val a = ByteArray(16) { (0x10 + it).toByte() }
    private val b = ByteArray(16) { (0x20 + it).toByte() }
    private val key = ByteArray(16) { (0x40 + it).toByte() }
    private fun bridge() = NearbyTcpControlBridge("SYNTHETIC", root, a, b)
    private fun frame(raw: ByteArray): NearbyFrame = NearbyFrameDecoder().let {
        it.feed(raw); assertNotNull(it.next()).also { _ -> assertNull(it.next()) }
    }
    private fun handshake() = NearbyFrame.plain(0, ByteWriter().tlv(2, byteArrayOf(2))
        .tlv(4, "SYNTHETIC_PHONE".encodeToByteArray()).tlv(6, byteArrayOf(1)).toByteArray()).encode()
    private fun encrypted(outer: Int, payload: ByteArray) = NearbyFrameCipher(root,a,b).let {
        try { it.seal(outer, payload, ByteArray(8) { 0x51 }).encode() } finally { it.close() }
    }
    private fun request(business: Int) = encrypted(2, encodeTlv(3,
        SocketMessages.encodeRequest(SocketMessages.Request(3,business,"SYNTHETIC".encodeToByteArray(),1,null))))

    @Test fun wifiStartsWithPinnedPlainConnectAndInitiatorWithoutBluetoothAddress() {
        val s=bridge(); val events=s.start(7,9,100,1,key)
        assertEquals(2,events.size)
        val first=frame(assertNotNull(events[0].frame));assertFalse(first.isEncrypted)
        assertEquals(15,Tlv.parseAll(first.payload).single().tag)
        val second=frame(assertNotNull(events[1].frame));assertFalse(second.isEncrypted)
        // Independent TLV tags/values from pinned NearbySession.start(WIFI).
        val tlvs=Tlv.parseAll(second.payload)
        assertEquals(listOf(1,3,5),tlvs.map{it.tag})
        assertContentEquals(byteArrayOf(2),tlvs[0].value)
        assertContentEquals("SYNTHETIC".encodeToByteArray(),tlvs[1].value)
        assertContentEquals(byteArrayOf(1),tlvs[2].value)
        key.fill(0);assertTrue(s.hasPrivateKey);s.close();assertFalse(s.hasPrivateKey)
    }
    @Test fun fragmentedHandshakeAndCoalescedEncryptedRequestsNeverInventDmsdpListener() {
        val s=bridge();s.start(7,9,100,1,key)
        val out=handshake().flatMap { s.feed(7,9,byteArrayOf(it),2) }
        assertEquals(listOf("HANDSHAKE_COMPLETED"),out.map{it.kind})
        val requests=s.feed(7,9,request(19)+request(20),3)
        assertEquals(listOf("SEND_FRAME","SOCKET_REQUEST_REJECTED","SEND_FRAME","SOCKET_REQUEST_REJECTED"),requests.map{it.kind})
        val cipher=NearbyFrameCipher(root,a,b)
        for((i,event) in requests.filter{it.kind=="SEND_FRAME"}.withIndex()) {
            val f=frame(assertNotNull(event.frame));assertTrue(f.isEncrypted)
            val r=SocketMessages.parseResponse(Tlv.parseAll(cipher.open(f)).single().value)
            assertEquals(listOf(1,0,3,19+i,0),listOf(r.status,r.port,r.channel,r.businessId,r.protocol))
        }
        cipher.close();s.close()
    }
    @Test fun protocolDisconnectSendsEncryptedAckBeforeWipingKey() {
        val s=bridge();s.start(7,9,100,1,key);s.feed(7,9,handshake(),2)
        val out=s.feed(7,9,encrypted(33,encodeTlv(5)),3)
        assertEquals(listOf("SEND_FRAME","TCP_DISCONNECT"),out.map{it.kind})
        val cipher=NearbyFrameCipher(root,a,b)
        assertContentEquals(encodeTlv(6),cipher.open(frame(assertNotNull(out[0].frame))))
        assertFalse(s.hasPrivateKey);cipher.close()
        assertEquals("TCP_REJECTED",s.tick(7,9,4).single().kind)
    }
    @Test fun originalDeadlineStaleGenerationIncarnationAndTimeReversalRevoke() {
        for((g,c,now) in listOf(Triple(7L,9L,100L),Triple(8L,9L,2L),Triple(7L,10L,2L),Triple(7L,9L,0L))) {
            val s=bridge();s.start(7,9,100,1,key)
            assertEquals("TCP_REJECTED",s.feed(g,c,handshake(),now).single().kind)
            assertFalse(s.hasPrivateKey)
        }
    }
    @Test fun cancellationAtTransferAndReplayNeverReauthorizeOrRetainKey() {
        val s=bridge();s.close();assertEquals("TCP_REJECTED",s.start(7,9,100,1,key).single().kind)
        assertFalse(s.hasPrivateKey)
        val replay=bridge();replay.start(7,9,100,1,key)
        assertEquals("TCP_REJECTED",replay.start(7,9,200,2,key).single().kind)
        assertFalse(replay.hasPrivateKey)
        assertFalse(replay.toString().contains("4041"))
    }
    @Test fun handshakeTimeoutAndFeedBeforeActivationCannotRetainAuthority() {
        val s=bridge();s.start(7,9,10000,1,key)
        assertEquals("TCP_REJECTED",s.tick(7,9,5001).single().kind)
        assertFalse(s.hasPrivateKey)
        val early=bridge()
        assertEquals("TCP_REJECTED",early.feed(7,9,handshake(),1).single().kind)
        assertFalse(early.hasPrivateKey)
    }
    @Test fun malformedCrcOversizeAndUnexpectedWifiPayloadTerminateWithoutSecretDiagnostics() {
        for(input in listOf(handshake().also { it[it.lastIndex]=(it.last().toInt() xor 1).toByte() },
                ByteArray(65537),encrypted(33,encodeTlv(5,byteArrayOf(1))))) {
            val s=bridge();s.start(7,9,100,1,key)
            assertEquals("TCP_REJECTED",s.feed(7,9,input,2).single().kind)
            assertFalse(s.hasPrivateKey)
        }
    }
}
