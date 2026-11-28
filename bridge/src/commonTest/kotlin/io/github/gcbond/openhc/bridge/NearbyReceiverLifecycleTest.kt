package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.bridge.auth.invoke
import io.github.gcbond.openhc.core.common.ByteWriter
import io.github.gcbond.openhc.core.common.codec.Crc16Arc
import io.github.gcbond.openhc.core.nearby.*
import kotlin.test.*

class NearbyReceiverLifecycleTest {
    private val root=ByteArray(16)
    private val a=ByteArray(16){(0x10+it).toByte()}
    private val b=ByteArray(16){(0x20+it).toByte()}
    private val key=ByteArray(16){0x41}
    private fun bridge():NearbyTcpControlBridge {
        val s=NearbyTcpControlBridge("SYNTHETIC",root,a,b)
        s.start(7,9,50000,1,key)
        s.feed(7,9,encrypted(0,ByteWriter().tlv(2,byteArrayOf(2)).tlv(4,byteArrayOf(0x53))
            .tlv(6,byteArrayOf(1)).toByteArray()),2)
        return s
    }
    private fun encrypted(type:Int,data:ByteArray)=NearbyFrameCipher(root,a,b).let {
        try{it.seal(type,data,ByteArray(8){0x51}).encode()}finally{it.close()}
    }
    private fun request(channel:Int=3,business:Int=20,tag:String="DMSDP",protocol:Int=1,outer:Int=4)=encrypted(outer,encodeTlv(3,
        SocketMessages.encodeRequest(SocketMessages.Request(channel,business,tag.encodeToByteArray(),protocol,null))))
    private fun negotiation():ByteArray {
        val head=byteArrayOf(0x7f,0x81.toByte(),0x90.toByte())+ByteArray(16)
        val crc=Crc16Arc.compute(head);return head+byteArrayOf(crc.toByte(),(crc ushr 8).toByte())
    }
    private fun frame(data:ByteArray):ByteArray=byteArrayOf(0,(data.size ushr 8).toByte(),data.size.toByte())+data
    private fun setup():NearbyTcpControlBridge {
        val s=bridge();assertEquals("DMSDP_LISTEN",s.feed(7,9,request(),3).single().kind)
        s.listenerReady(7,9,1,1234,3);s.endpointConnected(7,9,1,3)
        assertEquals(2,s.endpointData(7,9,1,negotiation(),3).single().channel)
        s.listenerReady(7,9,2,2345,3);return s
    }
    private fun select(udp:String="0")=frame("SET_PARAMETER * DMSDP/1.0\r\nCSeq: 2\r\nCryptoVer: 1\r\nCryptoSwitch: 222\r\nCryptoAlg: aes128-ctr\r\nUdpKA: $udp\r\n\r\n".encodeToByteArray())

    @Test fun exactResourceRequestWaitsForActualReadyAndRepeatsSamePort() {
        val s=bridge()
        assertEquals(listOf("DMSDP_LISTEN"),s.feed(7,9,request(),3).map{it.kind})
        assertTrue(s.feed(7,9,request(outer=2),3).isEmpty())
        val replies=s.listenerReady(7,9,1,1234,3);assertEquals(2,replies.size)
        val cipher=NearbyFrameCipher(root,a,b)
        for((i,event) in replies.withIndex()) {
            val decoder=NearbyFrameDecoder();decoder.feed(assertNotNull(event.frame));val f=assertNotNull(decoder.next())
            assertEquals(if(i==0)4 else 2,f.outerType)
            val r=SocketMessages.parseResponse(Tlv.parseAll(cipher.open(f)).single().value)
            assertEquals(listOf(0,1234,3,20,1),listOf(r.status,r.port,r.channel,r.businessId,r.protocol))
            assertContentEquals("DMSDP".encodeToByteArray(),r.tag)
        }
        assertEquals("SEND_FRAME",s.feed(7,9,request(),3).single().kind)
        cipher.close();s.close()
    }
    @Test fun wrongBusinessChannelTagAndProtocolNeverOpenListener() {
        for(req in listOf(request(channel=6),request(business=19),request(tag="dmsdp"),request(protocol=0))) {
            val s=bridge();assertEquals(listOf("SEND_FRAME","SOCKET_REQUEST_REJECTED"),s.feed(7,9,req,3).map{it.kind});s.close()
        }
    }
    @Test fun pendingControlEofFailsButAnsweredListenerKeepsOriginalPrivateKey() {
        val early=bridge();early.feed(7,9,request(),3)
        assertEquals("TCP_REJECTED",early.controlClosed(7,9,3).single().kind);assertFalse(early.hasPrivateKey)
        val s=bridge();s.feed(7,9,request(),3);s.listenerReady(7,9,1,1234,3)
        assertEquals("TCP_CONTROL_DETACHED",s.controlClosed(7,9,3).single().kind);assertTrue(s.hasPrivateKey)
        assertEquals("TCP_REJECTED",s.tick(7,9,50000).single().kind);assertFalse(s.hasPrivateKey)
    }
    @Test fun sessionFragmentsAndCoalescingWaitForSecondActualListener() {
        val s=bridge();s.feed(7,9,request(),3);s.listenerReady(7,9,1,1234,3);s.endpointConnected(7,9,1,3)
        val out=(negotiation()+negotiation()).flatMap{s.endpointData(7,9,1,byteArrayOf(it),3)}
        assertEquals(listOf("DMSDP_LISTEN"),out.map{it.kind})
        val replies=s.listenerReady(7,9,2,2345,3);assertEquals(2,replies.size)
        val expected=negotiation().also {it[4]=9;it[5]=0x29;val crc=Crc16Arc.compute(it,0,it.size-2);it[it.size-2]=crc.toByte();it[it.size-1]=(crc ushr 8).toByte()}
        replies.forEach{assertContentEquals(expected,it.frame)}
        assertTrue(s.endpointClosed(7,9,1,3).isEmpty())
        assertEquals("DMSDP_WRITE",s.endpointConnected(7,9,2,3).single().kind);s.close()
    }
    @Test fun malformedCrcDuplicateAndSessionPartialEofRevoke() {
        for(mode in 0..2) {
            val s=setup()
            val out=when(mode) {
                0->s.endpointData(7,9,1,negotiation().also{it[it.lastIndex]=(it.last().toInt() xor 1).toByte()},3)
                1->s.endpointConnected(7,9,1,3)
                else->{s.endpointData(7,9,1,byteArrayOf(0x7f),3);s.endpointClosed(7,9,1,3)}
            }
            assertEquals("TCP_REJECTED",out.single().kind);assertFalse(s.hasPrivateKey)
        }
    }
    @Test fun cryptoPlainAckThenEncryptedTcpKeepAliveAndNoMediaClaim() {
        val s=setup();val options=assertNotNull(s.endpointConnected(7,9,2,3).single().frame)
        assertEquals(0,options[0].toInt());assertTrue(options.decodeToString().contains("UdpKA: 0"))
        val events=select().flatMap{s.endpointData(7,9,2,byteArrayOf(it),4)}
        assertEquals(listOf("DMSDP_WRITE","DMSDP_ENCRYPTED"),events.map{it.kind})
        assertEquals(0,assertNotNull(events[0].frame)[0].toInt())
        val text="GET_PARAMETER * DMSDP/1.0\r\nCSeq: 3\r\n\r\n".encodeToByteArray();val iv=ByteArray(16){0x51}
        val cipher=assertNotNull(invoke(14,key=key,a=iv,c=text,size=text.size))
        val raw=byteArrayOf(0xab.toByte(),0,(iv.size+cipher.size).toByte())+iv+cipher
        assertTrue(s.endpointData(7,9,2,raw,5).isEmpty())
        val reply=assertNotNull(s.tick(7,9,1004).single().frame);assertEquals(0xab,reply[0].toInt() and 255)
        val decoded=invoke(14,key=key,a=reply.copyOfRange(3,19),c=reply.copyOfRange(19,reply.size),size=reply.size-19)
        assertTrue(assertNotNull(decoded).decodeToString().startsWith("GET_PARAMETER * DMSDP/1.0"))
        assertEquals("TCP_REJECTED",s.endpointClosed(7,9,2,1004).single().kind);assertFalse(s.hasPrivateKey)
    }
    @Test fun ctrMatchesIndependentNistSp80038aF5Vector() {
        fun hex(s:String)=s.chunked(2).map{it.toInt(16).toByte()}.toByteArray()
        val result=invoke(14,key=hex("2b7e151628aed2a6abf7158809cf4f3c"),a=hex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff"),
            c=hex("6bc1bee22e409f96e93d7e117393172a"),size=16)
        assertContentEquals(hex("874d6191b620e3261bef6864990db6ce"),result)
    }
    @Test fun coalescedSelectionAndCiphertextSwitchBetweenFrames() {
        val s=setup();s.endpointConnected(7,9,2,3)
        val iv=ByteArray(16){0x33}
        val text="GET_PARAMETER * DMSDP/1.0\r\nCSeq: 3\r\n\r\n".encodeToByteArray()
        val cipher=assertNotNull(invoke(14,key=key,a=iv,c=text,size=text.size))
        val data=select()+byteArrayOf(0xab.toByte(),0,(iv.size+cipher.size).toByte())+iv+cipher
        assertEquals(listOf("DMSDP_WRITE","DMSDP_ENCRYPTED"),s.endpointData(7,9,2,data,4).map{it.kind})
        assertEquals("DMSDP_WRITE",s.tick(7,9,1004).single().kind)
        s.close()
    }
    @Test fun tenMissedKeepAliveRoundsTerminateWithoutExtendingOwner() {
        val s=setup();s.endpointConnected(7,9,2,3);s.endpointData(7,9,2,select(),4)
        repeat(9){assertTrue(s.tick(7,9,1004+it*1000L).isEmpty())}
        assertEquals("TCP_REJECTED",s.tick(7,9,10004).single().kind)
        assertFalse(s.hasPrivateKey)
    }
    @Test fun ctrMatchesIndependentCounterCarryVector() {
        fun hex(s:String)=s.chunked(2).map{it.toInt(16).toByte()}.toByteArray()
        val result=invoke(14,key=ByteArray(16),a=ByteArray(16){0xff.toByte()},c=ByteArray(32),size=32)
        assertContentEquals(hex("3f5b8cc9ea855a0afa7347d23e8d664e66e94bd4ef8a2c3b884cfa59ca342b2e"),result)
    }
    @Test fun originalOwnerMismatchAndCancellationCannotReauthorizeEndpoint() {
        val s=setup();assertEquals("TCP_REJECTED",s.endpointConnected(8,9,2,3).single().kind)
        assertFalse(s.hasPrivateKey);assertEquals("TCP_REJECTED",s.listenerReady(7,9,2,9999,4).single().kind)
        val cancelled=setup();cancelled.close();assertEquals("TCP_REJECTED",cancelled.endpointConnected(7,9,2,3).single().kind)
    }
    @Test fun unsupportedUdpAndMalformedCryptoCannotAcknowledgeOrRetainKey() {
        for(data in listOf(select("1"),
                frame("SET_PARAMETER * DMSDP/1.0\r\nCSeq: 1\r\nCSeq: 2\r\n\r\n".encodeToByteArray()),
                byteArrayOf(0xab.toByte(),0,1,0))) {
            val s=setup();s.endpointConnected(7,9,2,3)
            assertEquals("TCP_REJECTED",s.endpointData(7,9,2,data,4).single().kind);assertFalse(s.hasPrivateKey)
        }
    }
    @Test fun capabilityBoundaryAndPendingFloodCloseWithoutClaimingMedia() {
        val s=setup();s.endpointConnected(7,9,2,3);s.endpointData(7,9,2,select(),4)
        val iv=ByteArray(16){0x31};val record=byteArrayOf(0x24,0,0,0,1,0,0,0,0,0,0)
        val cipher=assertNotNull(invoke(14,key=key,a=iv,c=record,size=record.size))
        val out=s.endpointData(7,9,2,byteArrayOf(0xab.toByte(),0,(16+cipher.size).toByte())+iv+cipher,5)
        assertEquals(listOf("DMSDP_CAPABILITY_REQUIRED"),out.map{it.kind});assertFalse(s.hasPrivateKey)
        val flood=bridge();repeat(8){flood.feed(7,9,request(),3)}
        assertEquals("TCP_REJECTED",flood.feed(7,9,request(),3).single().kind);assertFalse(flood.hasPrivateKey)
    }
}
