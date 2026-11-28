package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.common.ByteWriter
import io.github.gcbond.openhc.core.nearby.*
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import kotlin.test.*

/** Actual JVM bridge and real loopback streams. Provider/owner cancellation are injected;
 * native owner/daemon integration is exercised separately by the Simulator matrix. */
class NearbyTcpSocketTest {
    private val root=ByteArray(16)
    private val a=ByteArray(16){(0x10+it).toByte()}
    private val b=ByteArray(16){(0x20+it).toByte()}
    private fun read(s:Socket):NearbyFrame {
        val decoder=NearbyFrameDecoder()
        while(true) {
            val byte=s.getInputStream().read();check(byte>=0)
            decoder.feed(byteArrayOf(byte.toByte()));decoder.next()?.let{return it}
        }
    }
    @Test fun ownedSocketRunsEncryptedControlThenAckBeforeClose() {
        exercise("disconnect")
    }
    @Test fun originalExpiryClosesOwnedSocketAndRevokesKey() { exercise("expiry") }
    @Test fun ownerCancellationClosesOwnedSocketAndRevokesKey() { exercise("cancel") }
    @Test fun peerEofClosesOwnedSocketAndRevokesKey() { exercise("eof") }
    @Test fun independentPythonOpenSslPeerRunsActualJvmEncryptedSocket() { exercise("independent") }

    @Test fun independentPeerUsesRealSessionAndControlListenersUnderSameBridgeAndKey() {
        val link=NearbyTcpControlBridge("CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F",root,a,b)
        assertTrue(link.configureReceiver(NearbyReceiverDeviceConfig(
            io.github.gcbond.openhc.core.common.identity.HostIdentity("A1B2C3","D4","Synthetic","Synthetic"),
            "CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F",
            "A0:B1:C2:D3:E4:F5","127.0.0.1","127.0.0.1")))
        val listener=ServerSocket(0,1,InetAddress.getByName("127.0.0.1"));listener.soTimeout=3000
        val listeners=linkedMapOf<Int,ServerSocket>();val sockets=linkedMapOf<Int,Socket>()
        var failure:Throwable?=null;val cancel=AtomicBoolean(false)
        val start=System.nanoTime();fun now()=(System.nanoTime()-start)/1_000_000
        val worker=thread(name="owned-receiver-test") {
            try {listener.accept().use { main ->
                main.soTimeout=5;var detached=false;var running=true
                fun events(batch:List<Fe35ControlBridgeEvent>) {
                    for(event in batch) when(event.kind) {
                        "SEND_FRAME" -> {main.getOutputStream().write(assertNotNull(event.frame));main.getOutputStream().flush()}
                        "DMSDP_LISTEN" -> {
                            check(event.channel !in listeners)
                            val opened=ServerSocket(0,1,InetAddress.getByName("127.0.0.1"));opened.soTimeout=1
                            listeners[event.channel]=opened
                            events(link.listenerReady(1,1,event.channel,opened.localPort,now()))
                        }
                        "DMSDP_WRITE" -> {
                            val owned=checkNotNull(sockets[event.channel]);owned.getOutputStream().write(assertNotNull(event.frame));owned.getOutputStream().flush()
                        }
                        "TCP_CONTROL_DETACHED" -> detached=true
                        "TCP_REJECTED","TCP_DISCONNECT","DMSDP_CAPABILITY_REQUIRED",
                        "DMSDP_CONFIG_REQUIRED","DMSDP_HISIGHT_REQUIRED" -> running=false
                    }
                }
                val key=ByteArray(16){0x41}
                try{events(link.start(1,1,8000,now(),key))}finally{key.fill(0)}
                val data=ByteArray(4096)
                while(running && !cancel.get()) {
                    events(link.tick(1,1,now()));if(!running)break
                    if(!detached) {
                        val n=try{main.getInputStream().read(data)}catch(_:SocketTimeoutException){-2}
                        if(n==-1) events(link.controlClosed(1,1,now()))
                        else if(n>0) events(link.feed(1,1,data.copyOf(n),now()))
                    }
                    for((endpoint,opened) in listeners.toList()) {
                        if(endpoint !in sockets) {
                            val accepted=try{opened.accept()}catch(_:SocketTimeoutException){null}
                            if(accepted!=null) {accepted.soTimeout=1;sockets[endpoint]=accepted;events(link.endpointConnected(1,1,endpoint,now()))}
                        }
                        val owned=sockets[endpoint]?:continue
                        if(owned.isClosed)continue
                        val n=try{owned.getInputStream().read(data)}catch(_:SocketTimeoutException){-2}
                        if(n==-1) {owned.close();events(link.endpointClosed(1,1,endpoint,now()))}
                        else if(n>0)events(link.endpointData(1,1,endpoint,data.copyOf(n),now()))
                    }
                }
            }}catch(t:Throwable){failure=t}
            finally{link.close();sockets.values.forEach{it.close()};listeners.values.forEach{it.close()};listener.close()}
        }
        try {
            val script=listOf(File("scripts/nearby-tcp-test-phone.py"),File("../scripts/nearby-tcp-test-phone.py")).first{it.isFile}.absolutePath
            val phone=ProcessBuilder("python",script,listener.localPort.toString(),"dmsdp").redirectErrorStream(true).start()
            try {
                assertTrue(phone.waitFor(12,TimeUnit.SECONDS),"bounded independent DMSDP peer")
                val result=phone.inputStream.bufferedReader().readText();assertEquals(0,phone.exitValue(),result)
                assertTrue(result.contains("NEARBY_PYTHON_OPENSSL_JVM_SOCKET_OK"))
            }finally{if(phone.isAlive){phone.destroyForcibly();phone.waitFor(2,TimeUnit.SECONDS)}}
        }finally{
            cancel.set(true);worker.join(3500);assertFalse(worker.isAlive);assertFalse(link.hasPrivateKey)
            failure?.let{throw AssertionError("owned receiver worker failed",it)}
        }
    }

    private fun exercise(end:String) {
        val link=NearbyTcpControlBridge("CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F",root,a,b)
        val cancel=AtomicBoolean(false)
        val start=System.nanoTime()
        fun now()=(System.nanoTime()-start)/1_000_000
        val listener=ServerSocket(0,1,InetAddress.getByName("127.0.0.1"))
        listener.soTimeout=3000
        var failure:Throwable?=null
        val worker=thread(name="owned-test-tcp") {
            try {
                listener.accept().use { owned ->
                    owned.soTimeout=20
                    fun send(events:List<Fe35ControlBridgeEvent>):Boolean {
                        for(event in events) {
                            if(cancel.get()) return false
                            if(event.kind=="SEND_FRAME") {
                                owned.getOutputStream().write(assertNotNull(event.frame))
                                owned.getOutputStream().flush()
                            } else if(event.kind in listOf("TCP_REJECTED","TCP_DISCONNECT")) return false
                        }
                        return true
                    }
                    val key=ByteArray(16){0x41}
                    try {
                        if(!send(link.start(1,1,1500,now(),key))) return@use
                    } finally {key.fill(0)}
                    val bytes=ByteArray(1024)
                    while(!cancel.get()) {
                        if(!send(link.tick(1,1,now()))) break
                        val n=try {owned.getInputStream().read(bytes)} catch(_:SocketTimeoutException){continue}
                        if(n<0) break
                        if(!send(link.feed(1,1,bytes.copyOf(n),now()))) break
                    }
                }
            } catch(t:Throwable) {failure=t}
            finally {link.close();listener.close()}
        }
        try {
            if(end=="independent") {
                val script=listOf(File("scripts/nearby-tcp-test-phone.py"),File("../scripts/nearby-tcp-test-phone.py"))
                    .first{it.isFile}.absolutePath
                val phone=ProcessBuilder("python",script,listener.localPort.toString()).redirectErrorStream(true).start()
                try {
                    assertTrue(phone.waitFor(6,TimeUnit.SECONDS),"bounded independent test peer")
                    val evidence=phone.inputStream.bufferedReader().readText()
                    assertEquals(0,phone.exitValue(),evidence)
                    assertTrue(evidence.contains("NEARBY_PYTHON_OPENSSL_JVM_SOCKET_OK"))
                } finally { if(phone.isAlive) {phone.destroyForcibly();phone.waitFor(2,TimeUnit.SECONDS)} }
                return
            }
            Socket("127.0.0.1",listener.localPort).use { phone ->
                phone.soTimeout=3000
                assertFalse(read(phone).isEncrypted);assertFalse(read(phone).isEncrypted)
                val cipher=NearbyFrameCipher(root,a,b)
                try {
                    val handshake=ByteWriter().tlv(2,byteArrayOf(2)).tlv(4,byteArrayOf(0x53))
                        .tlv(6,byteArrayOf(1)).toByteArray()
                    val raw=cipher.seal(0,handshake,ByteArray(8){0x31}).encode()
                    phone.getOutputStream().write(raw,0,3);phone.getOutputStream().flush()
                    phone.getOutputStream().write(raw,3,raw.size-3)
                    val req=encodeTlv(3,SocketMessages.encodeRequest(SocketMessages.Request(3,20,byteArrayOf(0x53),1,null)))
                    phone.getOutputStream().write(cipher.seal(2,req,ByteArray(8){0x32}).encode())
                    val reply=read(phone);assertTrue(reply.isEncrypted)
                    assertEquals(1,SocketMessages.parseResponse(Tlv.parseAll(cipher.open(reply)).single().value).status)
                    when(end) {
                        "disconnect" -> {
                            phone.getOutputStream().write(cipher.seal(33,encodeTlv(5),ByteArray(8){0x33}).encode())
                            assertContentEquals(encodeTlv(6),cipher.open(read(phone)))
                        }
                        "cancel" -> cancel.set(true)
                        "eof" -> phone.shutdownOutput()
                    }
                    assertEquals(-1,phone.getInputStream().read())
                } finally {cipher.close()}
            }
        } finally {
            cancel.set(true);worker.join(3500)
            assertFalse(worker.isAlive,"owned worker terminated")
            assertFalse(link.hasPrivateKey)
            failure?.let{throw AssertionError("owned socket worker failed",it)}
        }
    }
}
