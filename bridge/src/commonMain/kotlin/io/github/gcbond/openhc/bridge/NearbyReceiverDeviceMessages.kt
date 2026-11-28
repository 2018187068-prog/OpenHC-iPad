package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.common.codec.Ea
import io.github.gcbond.openhc.core.common.codec.Ipv4Text
import io.github.gcbond.openhc.core.common.identity.BluetoothAddress
import io.github.gcbond.openhc.core.common.identity.HostIdentity
import io.github.gcbond.openhc.core.nearby.Fe35SessionEvent
import kotlinx.serialization.json.*

/** Existing authorized in-memory identity plus actual accepted socket addresses.
 * No identity discovery, service capability or media sink is supplied here. */
class NearbyReceiverDeviceConfig(val host: HostIdentity, val deviceId: String,
    bluetoothMac: String, val localIp: String, val phoneIp: String) {
    val bluetoothMac=BluetoothAddress.format(BluetoothAddress.parse(bluetoothMac))
    init {
        require(deviceId.isNotEmpty() && deviceId.length<=64)
        require(this.bluetoothMac!=BluetoothAddress.UNAVAILABLE)
        require(Ipv4Text.isCanonical(localIp) && Ipv4Text.isCanonical(phoneIp))
    }
    internal fun deviceObject()=buildJsonObject {
        put("deviceId",deviceId);put("deviceName",host.deviceName);put("deviceType",4)
        put("bluetoothMac",bluetoothMac);put("btName",host.deviceName)
        put("localIp",localIp);put("remoteIp",phoneIp);put("port",-1);put("businessId",1)
        put("properties",buildJsonObject {put("2003",host.fullModel)})
    }
    override fun toString()="NearbyReceiverDeviceConfig(redacted; services=0)"
}

/** Pinned '$'/BE32 module/BE32 signed type/BE16 length records. Parse the whole
 * encrypted payload before applying any commands; never expose peer payloads. */
internal object NearbyDeviceRecords {
    class Record(val module: Long,val type: Int,val data: ByteArray)
    fun parse(bytes: ByteArray):List<Record> {
        require(bytes.isNotEmpty())
        val out=arrayListOf<Record>();var at=0
        try { while(at<bytes.size) {
            require(out.size<32 && bytes.size-at>=11 && bytes[at]==0x24.toByte())
            val module=u32(bytes,at+1);val type=u32(bytes,at+5).toInt()
            val count=((bytes[at+9].toInt() and 255) shl 8) or (bytes[at+10].toInt() and 255)
            require(count<=bytes.size-at-11)
            out+=Record(module,type,bytes.copyOfRange(at+11,at+11+count));at+=11+count
        }
        return out
        } catch(error:Exception) {out.forEach{it.data.fill(0)};throw error}
    }
    fun encode(module: Long,type: Int,data: ByteArray):ByteArray {
        require(module in 0..0xffffffffL && data.isNotEmpty() && data.size<=65508)
        val out=ByteArray(11+data.size);out[0]=0x24
        for(i in 0..3) {out[1+i]=(module ushr (24-i*8)).toByte();out[5+i]=(type ushr (24-i*8)).toByte()}
        out[9]=(data.size ushr 8).toByte();out[10]=data.size.toByte();data.copyInto(out,11)
        return out
    }
    fun u32(bytes: ByteArray,at: Int):Long {
        require(at>=0 && bytes.size-at>=4)
        var n=0L;for(i in at until at+4)n=(n shl 8) or (bytes[i].toLong() and 255);return n
    }
    fun ea(bytes: ByteArray,at: Int):Pair<Int,Int> {
        val value=Ea.decode(bytes,at,bytes.size);require(value>=0)
        return Ea.valueOf(value) to (at+Ea.sizeOf(value))
    }
}

/** Device module3/type-1 commands101..105. No local media services exist yet,
 * so request104 legitimately returns no102 and no readiness claim. */
internal class NearbyReceiverDeviceMessages(private val config:NearbyReceiverDeviceConfig) {
    private var peerId:String?=null
    private var localInfoSent=false
    fun handle(data:ByteArray):List<Fe35SessionEvent> {
        val(command,at)=NearbyDeviceRecords.ea(data,0)
        val body=data.copyOfRange(at,data.size)
        try {return when(command) {
            101 -> {
                val obj=json(body);val id=identity(obj,"deviceId")
                integer(obj,"deviceType");objectField(obj,"properties")
                check(peerId==null || peerId==id);peerId=id
                val out=arrayListOf<Fe35SessionEvent>()
                if(!localInfoSent) {
                    val encoded=Ea.encode(101)+config.deviceObject().toString().encodeToByteArray()
                    try {out+=Fe35SessionEvent("DMSDP_RECORD_REPLY",frame=NearbyDeviceRecords.encode(3,-1,encoded))}
                    finally {encoded.fill(0)}
                    localInfoSent=true
                }
                out+=Fe35SessionEvent("DMSDP_PEER_DEVICE_INFO");out
            }
            102 -> {service(json(body));listOf(Fe35SessionEvent("DMSDP_PEER_SERVICE_INFO"))}
            103 -> {
                require(body.size>4);val encoded=body.copyOfRange(4,body.size)
                val obj=try {json(encoded)} finally {encoded.fill(0)}
                service(obj);require(obj.containsKey("deviceName"))
                listOf(Fe35SessionEvent("DMSDP_SERVICE_STATUS"))
            }
            104 -> {require(body.size==4);listOf(Fe35SessionEvent("DMSDP_SERVICES_EMPTY"))}
            105 -> {require(body.size==4);listOf(Fe35SessionEvent("DMSDP_DISCONNECT_NOTIFIED"))}
            else -> listOf(Fe35SessionEvent("DMSDP_CAPABILITY_REQUIRED"))
        }} finally {body.fill(0)}
    }
    fun close() {peerId=null}
    private fun json(bytes:ByteArray):JsonObject=try {
        Json.parseToJsonElement(bytes.decodeToString(throwOnInvalidSequence=true)) as? JsonObject
            ?: error("DMSDP_JSON_REJECTED")
    } catch(_:Exception) {throw IllegalArgumentException("DMSDP_JSON_REJECTED")}
    private fun identity(obj:JsonObject,name:String):String {
        val value=obj[name] as? JsonPrimitive
        require(value!=null && value.isString && value.content.isNotEmpty());return value.content
    }
    private fun integer(obj:JsonObject,name:String):Long=
        (obj[name] as? JsonPrimitive)?.takeUnless{it.isString}?.longOrNull ?: error("DMSDP_JSON_REJECTED")
    private fun objectField(obj:JsonObject,name:String) {require(obj[name]==null || obj[name] is JsonObject)}
    private fun service(obj:JsonObject) {
        identity(obj,"deviceId");identity(obj,"serviceId");integer(obj,"serviceType")
        objectField(obj,"properties");objectField(obj,"status")
    }
}
