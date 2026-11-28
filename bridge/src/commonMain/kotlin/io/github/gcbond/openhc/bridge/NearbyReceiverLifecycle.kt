package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.bridge.auth.invoke
import io.github.gcbond.openhc.core.common.codec.Crc16Arc
import io.github.gcbond.openhc.core.common.codec.Ea
import io.github.gcbond.openhc.core.common.codec.ReceiveBuffer
import io.github.gcbond.openhc.core.nearby.Fe35SessionEvent
import io.github.gcbond.openhc.core.nearby.nearbySecureRandomBytes

/** Pinned ReceiverSession/DmsdpSession WiFi setup slice. No device/service/media capability
 * declaration. The enclosing bridge owns the original generation, lease and private key.
 * Endpoints 1/2 are DMSDP session/control, never the Nearby control stream. */
internal class NearbyReceiverLifecycle(private val key: () -> ByteArray) {
    private val session = ReceiveBuffer()
    private val control = ReceiveBuffer()
    private var sessionConnected = false
    private var sessionClosed = false
    private var controlConnected = false
    private var controlRequested = false
    private var pending = 0
    private var port = 0
    private var encrypted = false
    private var keepAliveAt = 0L
    private var alive = false
    private var heard = false
    private var misses = 0
    private var sequence = 2
    private var devices:NearbyReceiverDeviceMessages?=null
    fun configure(config:NearbyReceiverDeviceConfig) {check(devices==null);devices=NearbyReceiverDeviceMessages(config)}

    fun connected(endpoint: Int): List<Fe35SessionEvent> {
        if (endpoint == 1) { check(!sessionConnected); sessionConnected = true; return emptyList() }
        check(endpoint == 2 && port != 0 && !controlConnected)
        controlConnected = true
        return listOf(write(2, plain("OPTIONS * DMSDP/1.0\r\nCryptoVer: 1\r\nCryptoAbility: 222\r\nCryptoAlg: aes128-ctr\r\nUdpKA: 0\r\nKaRetry: 160\r\nLowDelay: 1\r\nCSeq: 1\r\n\r\n".encodeToByteArray())))
    }

    fun listenerReady(controlPort: Int): List<Fe35SessionEvent> {
        check(controlRequested && port == 0 && controlPort in 1..65535)
        port = controlPort
        val result = List(pending) { write(1, negotiation()) }; pending = 0
        return result
    }

    fun feed(endpoint: Int, bytes: ByteArray, now: Long): List<Fe35SessionEvent> {
        require(bytes.isNotEmpty() && bytes.size <= 65536)
        if (endpoint == 1) {
            check(sessionConnected && !sessionClosed)
            require(session.size + bytes.size <= 65536)
            session.append(bytes)
            val out = arrayListOf<Fe35SessionEvent>()
            while (session.size > 0) {
                require(session.byteAt(0) == 0x7f)
                val module = ea(session, 1) ?: break
                val length = ea(session, module.second) ?: break
                require(module.first == 1 && length.first == 16)
                val total = length.second + 18
                if (session.size < total) break
                val frame = session.copy(0, total)
                require(frame[length.second] == 0.toByte())
                val crc = Crc16Arc.compute(frame, 0, total - 2)
                require((frame[total-2].toInt() and 255) == (crc and 255) &&
                    (frame[total-1].toInt() and 255) == (crc ushr 8))
                session.consume(total); frame.fill(0)
                if (port > 0) out += write(1, negotiation()) else {
                    check(++pending <= 8)
                    if (!controlRequested) { controlRequested = true; out += Fe35SessionEvent("DMSDP_LISTEN", channel = 2) }
                }
            }
            return out
        }
        check(endpoint == 2 && controlConnected)
        require(control.size + bytes.size <= 65538)
        control.append(bytes)
        val out = arrayListOf<Fe35SessionEvent>()
        while (control.size >= 3) {
            val flag = control.byteAt(0)
            val size = (control.byteAt(1) shl 8) or control.byteAt(2)
            require(size > 0 && flag == if (encrypted) 0xab else 0)
            if (control.size < size + 3) break
            val raw = control.copy(3, size); control.consume(size + 3)
            val payload = if (encrypted) {
                require(raw.size > 16)
                val iv = raw.copyOfRange(0,16); val cipher = raw.copyOfRange(16,raw.size)
                try { ctr(iv,cipher) } finally { iv.fill(0);cipher.fill(0);raw.fill(0) }
            } else raw
            val events=try { message(payload, now) } finally { payload.fill(0) }
            out+=events
            if(events.any{terminal(it.kind)})break
        }
        return out
    }

    private fun message(bytes: ByteArray, now: Long): List<Fe35SessionEvent> {
        if (encrypted && bytes.firstOrNull() == 0x24.toByte()) return records(bytes)
        require(bytes.all { it.toInt() in 0..127 })
        val text = bytes.decodeToString()
        val split = text.indexOf("\r\n\r\n"); require(split >= 0)
        val lines = text.substring(0,split).split("\r\n")
        val headers = linkedMapOf<String,String>()
        for (line in lines.drop(1)) {
            val colon = line.indexOf(':'); require(colon > 0)
            val name = line.substring(0,colon).trim().lowercase()
            require(headers.put(name,line.substring(colon+1).trim()) == null)
        }
        val body = bytes.size - split - 4
        val declared = headers["content-length"]
        require(declared == null || (declared.isNotEmpty() && declared.all { it in '0'..'9' } && declared.toIntOrNull() == body))
        require(body == 0)
        val first = lines.first()
        if (first.startsWith("DMSDP/1.0 ") && !encrypted) return emptyList()
        val cseq = headers["cseq"] ?: error("DMSDP_CSEQ")
        require(cseq.isNotEmpty() && cseq.all { it in '0'..'9' } && cseq.length <= 10)
        if (!encrypted) {
            require(first == "SET_PARAMETER * DMSDP/1.0" && headers["cryptover"] == "1" &&
                headers["cryptoswitch"] == "222" && headers["cryptoalg"] == "aes128-ctr" &&
                headers["udpka"] in listOf(null,"0"))
            // Plain 200 precedes switching, as in pinned DmsdpSession.
            val ack = plain("DMSDP/1.0 200 OK\r\nCSeq: $cseq\r\nCryptoVer: 1\r\nCryptoSwitch: 222\r\nCryptoAlg: aes128-ctr\r\nPlatform: 0\r\n\r\n".encodeToByteArray())
            encrypted = true; keepAliveAt = now + 1000
            return listOf(write(2,ack), Fe35SessionEvent("DMSDP_ENCRYPTED"))
        }
        if (first == "GET_PARAMETER * DMSDP/1.0" && cseq.any { it != '0' }) {
            heard = true;alive = true;return emptyList()
        }
        if (first == "SET_PARAMETER * DMSDP/1.0" &&
            listOf("timeserverport","timeushigh","timeuslow").all {headers[it]!=null}) {
            // Pinned control ACK only. No new clock source, UDP connection or timer.
            return listOf(write(2,seal("DMSDP/1.0 200 OK\r\nCSeq: $cseq\r\n\r\n".encodeToByteArray())),
                Fe35SessionEvent("DMSDP_TIME_SYNC_ACKED"))
        }
        return listOf(Fe35SessionEvent("DMSDP_CAPABILITY_REQUIRED"))
    }

    private fun records(bytes:ByteArray):List<Fe35SessionEvent> {
        val parsed=NearbyDeviceRecords.parse(bytes);val out=arrayListOf<Fe35SessionEvent>()
        try {for(record in parsed) {
            val events=when {
                record.type == -1 && record.module==3L -> devices?.handle(record.data)
                    ?: listOf(Fe35SessionEvent("DMSDP_CONFIG_REQUIRED"))
                record.type == -1 && record.module==5L -> {
                    val(command,at)=NearbyDeviceRecords.ea(record.data,0)
                    if(command==101) {
                        val(port,end)=NearbyDeviceRecords.ea(record.data,at)
                        require(end==record.data.size && port in 1..65535)
                        listOf(Fe35SessionEvent("DMSDP_HISIGHT_REQUIRED",channel=port))
                    } else listOf(Fe35SessionEvent("DMSDP_CAPABILITY_REQUIRED"))
                }
                else -> listOf(Fe35SessionEvent("DMSDP_CAPABILITY_REQUIRED"))
            }
            for(event in events) {
                if(event.kind=="DMSDP_RECORD_REPLY") out+=write(2,seal(checkNotNull(event.frame)))
                else out+=event
            }
            if(events.any{terminal(it.kind)})break
        }} finally {parsed.forEach{it.data.fill(0)}}
        return out
    }

    fun tick(now: Long): List<Fe35SessionEvent> {
        if (!encrypted || now < keepAliveAt) return emptyList()
        if (alive) { misses = 0; alive = false } else check(++misses < 10)
        keepAliveAt = now + 1000
        if (!heard) return emptyList()
        val text = "GET_PARAMETER * DMSDP/1.0\r\nCSeq: ${sequence++}\r\n\r\n".encodeToByteArray()
        return listOf(write(2,seal(text)))
    }

    fun closed(endpoint: Int) {
        if (endpoint == 1) { check(sessionConnected && !sessionClosed && session.size == 0 && port != 0);sessionClosed = true }
        else error("DMSDP_CONTROL_CLOSED_BEFORE_MEDIA")
    }
    fun close() { session.array.fill(0); control.array.fill(0);session.clear();control.clear();devices?.close();devices=null }
    private fun terminal(kind:String)=kind in setOf("DMSDP_CONFIG_REQUIRED","DMSDP_HISIGHT_REQUIRED","DMSDP_CAPABILITY_REQUIRED")
    private fun seal(bytes:ByteArray):ByteArray {
        val iv=nearbySecureRandomBytes(16);var cipher:ByteArray?=null;var payload:ByteArray?=null
        try {
            require(bytes.isNotEmpty() && bytes.size<=65519)
            cipher=ctr(iv,bytes);payload=iv+cipher
            return framed(0xab,payload)
        } finally {iv.fill(0);bytes.fill(0);cipher?.fill(0);payload?.fill(0)}
    }
    private fun ctr(iv: ByteArray, input: ByteArray): ByteArray =
        invoke(14,key=key(),a=iv,c=input,size=input.size) ?: error("DMSDP_CTR_FAILED")
    private fun negotiation(): ByteArray {
        val body = byteArrayOf(0x7f,0x81.toByte(),0x90.toByte()) + ByteArray(16).also {
            it[1]=(port ushr 8).toByte();it[2]=port.toByte() }
        val crc = Crc16Arc.compute(body)
        return body + byteArrayOf(crc.toByte(),(crc ushr 8).toByte())
    }
    private fun ea(buffer: ReceiveBuffer, offset: Int): Pair<Int,Int>? {
        val v=Ea.decode(buffer.array,buffer.start+offset,buffer.end)
        require(v != Ea.UNTERMINATED)
        return if(v==Ea.NEED_MORE) null else Ea.valueOf(v) to (offset+Ea.sizeOf(v))
    }
    private fun plain(bytes: ByteArray) = framed(0,bytes)
    private fun framed(flag: Int, bytes: ByteArray) = byteArrayOf(flag.toByte(),(bytes.size ushr 8).toByte(),bytes.size.toByte())+bytes
    private fun write(endpoint: Int, bytes: ByteArray) = Fe35SessionEvent("DMSDP_WRITE",frame=bytes,channel=endpoint)
}
