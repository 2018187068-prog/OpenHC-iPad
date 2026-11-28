package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.bridge.auth.invoke
import io.github.gcbond.openhc.core.common.ByteWriter
import io.github.gcbond.openhc.core.common.codec.Crc16Arc
import io.github.gcbond.openhc.core.common.codec.Ea
import io.github.gcbond.openhc.core.common.identity.HostIdentity
import io.github.gcbond.openhc.core.nearby.*
import kotlinx.serialization.json.*
import kotlin.test.*

class NearbyReceiverLifecycleTest {
    private val root=ByteArray(16)
    private val a=ByteArray(16){(0x10+it).toByte()}
    private val b=ByteArray(16){(0x20+it).toByte()}
    private val key=ByteArray(16){0x41}
    private fun deviceConfig(id:String="SYNTHETIC")=NearbyReceiverDeviceConfig(
        HostIdentity("A1B2C3","D4","Synthetic","Synthetic"),id,"A0:B1:C2:D3:E4:F5","127.0.0.1","127.0.0.1")
    private fun bridge(configured:Boolean=false):NearbyTcpControlBridge {
        val s=NearbyTcpControlBridge("SYNTHETIC",root,a,b)
        if(configured)assertTrue(s.configureReceiver(deviceConfig()))
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
    private fun setup(configured:Boolean=false):NearbyTcpControlBridge {
        val s=bridge(configured);assertEquals("DMSDP_LISTEN",s.feed(7,9,request(),3).single().kind)
        s.listenerReady(7,9,1,1234,3);s.endpointConnected(7,9,1,3)
        assertEquals(2,s.endpointData(7,9,1,negotiation(),3).single().channel)
        s.listenerReady(7,9,2,2345,3);return s
    }
    private fun select(udp:String="0")=frame("SET_PARAMETER * DMSDP/1.0\r\nCSeq: 2\r\nCryptoVer: 1\r\nCryptoSwitch: 222\r\nCryptoAlg: aes128-ctr\r\nUdpKA: $udp\r\n\r\n".encodeToByteArray())
    private fun deviceReady(configured:Boolean=true)=setup(configured).also{
        it.endpointConnected(7,9,2,3);it.endpointData(7,9,2,select(),4)
    }
    private fun cipherFeed(s:NearbyTcpControlBridge,bytes:ByteArray):List<Fe35ControlBridgeEvent> {
        return s.endpointData(7,9,2,cipherFrame(bytes),5)
    }
    private fun cipherFrame(bytes:ByteArray):ByteArray {
        val iv=ByteArray(16){0x62};val data=iv+assertNotNull(invoke(14,key=key,a=iv,c=bytes,size=bytes.size))
        return byteArrayOf(0xab.toByte(),(data.size ushr 8).toByte(),data.size.toByte())+data
    }
    private fun open(event:Fe35ControlBridgeEvent):ByteArray {
        val raw=assertNotNull(event.frame);assertEquals(0xab,raw[0].toInt() and 255)
        return assertNotNull(invoke(14,key=key,a=raw.copyOfRange(3,19),c=raw.copyOfRange(19,raw.size),size=raw.size-19))
    }
    private fun command(n:Int,body:ByteArray)=NearbyDeviceRecords.encode(3,-1,Ea.encode(n)+body)
    private fun info(id:String="PHONE")=buildJsonObject{put("deviceId",id);put("deviceType",3)}.toString().encodeToByteArray()

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
    @Test fun recordWireUsesUnsignedModuleSignedTypeAndExactLengths() {
        val wire=byteArrayOf(0x24,0,0,0,3,-1,-1,-1,-1,0,1,0xe5.toByte())
        val r=NearbyDeviceRecords.parse(wire).single()
        assertEquals(3L,r.module);assertEquals(-1,r.type);assertContentEquals(byteArrayOf(0xe5.toByte()),r.data)
        assertContentEquals(wire,NearbyDeviceRecords.encode(3,-1,r.data))
        assertEquals(2,NearbyDeviceRecords.parse(wire+wire).size)
        for(bad in listOf(wire.copyOf(11),wire.copyOf(5),wire+byteArrayOf(0),wire.copyOf().also{it[0]=0}))
            assertFails{NearbyDeviceRecords.parse(bad)}
    }
    @Test fun receiverConfigIsOneShotSameIdentityAndRedacted() {
        val s=NearbyTcpControlBridge("SYNTHETIC",root,a,b)
        assertFalse(s.configureReceiver(deviceConfig("OTHER")))
        assertTrue(s.configureReceiver(deviceConfig()));assertFalse(s.configureReceiver(deviceConfig()))
        s.start(7,9,50000,1,key);assertFalse(s.configureReceiver(deviceConfig()));s.close()
        assertEquals("NearbyReceiverDeviceConfig(redacted; services=0)",deviceConfig().toString())
    }
    @Test fun device101RepliesOnceWithActualConfigurationAndNoMediaProperties() {
        val s=deviceReady();val first=cipherFeed(s,command(101,info()))
        assertEquals(listOf("DMSDP_WRITE","DMSDP_PEER_DEVICE_INFO"),first.map{it.kind})
        val r=NearbyDeviceRecords.parse(open(first[0])).single();val(cmd,at)=NearbyDeviceRecords.ea(r.data,0)
        assertEquals(101,cmd);val obj=Json.parseToJsonElement(r.data.copyOfRange(at,r.data.size).decodeToString()).jsonObject
        assertEquals(deviceConfig().deviceObject(),obj)
        assertEquals(setOf("2003"),obj.getValue("properties").jsonObject.keys)
        assertEquals(listOf("DMSDP_PEER_DEVICE_INFO"),cipherFeed(s,command(101,info())).map{it.kind});s.close()
    }
    @Test fun changedPeerIdentityAndMissingLocalConfigRevokeRatherThanEcho() {
        val s=deviceReady();cipherFeed(s,command(101,info()))
        assertEquals("TCP_REJECTED",cipherFeed(s,command(101,info("OTHER"))).single().kind);assertFalse(s.hasPrivateKey)
        val missing=deviceReady(false)
        assertEquals("DMSDP_CONFIG_REQUIRED",cipherFeed(missing,command(101,info())).single().kind);assertFalse(missing.hasPrivateKey)
    }
    @Test fun peerServiceCommandsAreValidatedButNoUnsupportedServiceIsAdvertised() {
        val s=deviceReady();val service=buildJsonObject{
            put("deviceId","PHONE");put("deviceName","Synthetic");put("serviceId","peer1");put("serviceType",8)
            put("properties",buildJsonObject{});put("status",buildJsonObject{})
        }.toString().encodeToByteArray()
        val data=command(102,service)+command(103,byteArrayOf(0,0,0,0xca.toByte())+service)+
            command(104,byteArrayOf(-1,-1,-1,-1))+command(105,byteArrayOf(0,0,0,1))
        assertEquals(listOf("DMSDP_PEER_SERVICE_INFO","DMSDP_SERVICE_STATUS","DMSDP_SERVICES_EMPTY","DMSDP_DISCONNECT_NOTIFIED"),
            cipherFeed(s,data).map{it.kind});assertTrue(s.hasPrivateKey);s.close()
    }
    @Test fun malformedDeviceJsonUtf8AndRecordLengthsFailClosed() {
        val badJson=listOf(byteArrayOf(0xff.toByte()),"[]".encodeToByteArray(),"{".encodeToByteArray(),
            buildJsonObject{put("deviceId","PHONE");put("deviceType","3")}.toString().encodeToByteArray())
        for(bytes in badJson) {val s=deviceReady();assertEquals("TCP_REJECTED",cipherFeed(s,command(101,bytes)).single().kind);assertFalse(s.hasPrivateKey)}
        for(n in listOf(103,104,105)) {val s=deviceReady();assertEquals("TCP_REJECTED",cipherFeed(s,command(n,byteArrayOf(0))).single().kind);assertFalse(s.hasPrivateKey)}
    }
    @Test fun timeSyncRespondsInExistingCipherWithoutNewAuthorityOrMediaClaim() {
        val s=deviceReady();val bytes="SET_PARAMETER * DMSDP/1.0\r\nTimeServerPort: 1234\r\nTimeUsHigh: 1\r\nTimeUsLow: -1\r\nCSeq: 8\r\n\r\n".encodeToByteArray()
        val result=cipherFeed(s,bytes);assertEquals(listOf("DMSDP_WRITE","DMSDP_TIME_SYNC_ACKED"),result.map{it.kind})
        assertEquals("DMSDP/1.0 200 OK\r\nCSeq: 8\r\n\r\n",open(result[0]).decodeToString())
        assertEquals("TCP_REJECTED",s.tick(7,9,50000).single().kind);assertFalse(s.hasPrivateKey)
    }
    @Test fun displayPortReachesExplicitHiSightBoundaryWithoutFakeReadiness() {
        val s=deviceReady();val request=NearbyDeviceRecords.encode(5,-1,Ea.encode(101)+Ea.encode(7236))
        val event=cipherFeed(s,request).single();assertEquals("DMSDP_HISIGHT_REQUIRED",event.kind);assertEquals(7236,event.channel);assertFalse(s.hasPrivateKey)
        for(data in listOf(Ea.encode(101),Ea.encode(101)+Ea.encode(0),Ea.encode(101)+Ea.encode(70000),Ea.encode(101)+Ea.encode(1)+byteArrayOf(0))) {
            val malformed=deviceReady();assertEquals("TCP_REJECTED",cipherFeed(malformed,NearbyDeviceRecords.encode(5,-1,data)).single().kind);assertFalse(malformed.hasPrivateKey)
        }
    }
    @Test fun terminalBoundaryStopsCoalescedRecordsAndControlFrames() {
        val boundary=NearbyDeviceRecords.encode(5,-1,Ea.encode(101)+Ea.encode(7236))
        val later=command(101,info())
        for(bytes in listOf(cipherFrame(boundary+later),cipherFrame(boundary)+cipherFrame(later))) {
            val s=deviceReady()
            assertEquals(listOf("DMSDP_HISIGHT_REQUIRED"),s.endpointData(7,9,2,bytes,5).map{it.kind})
            assertFalse(s.hasPrivateKey)
        }
    }
}
