package io.github.gcbond.openhc.core.nearby

/** Same Bluetooth control-session continuation. The trusted owner fences the one-shot key transfer;
 * this object creates no lease authority. Wire behavior: OpenHC 8132399 NearbySession and
 * WirelessReceiverSession. Boundary: owned TCP accept, before encrypted ControlLink processing. */
internal class NearbyWifiJoin(
    private val generation: Long, private val connection: Long,
    private val deadline: Long, now: Long,
    private val send: (Int, ByteArray) -> Fe35SessionEvent,
) {
    private var last = now
    private var closed = false
    private var info: WifiConnectionInfo? = null
    private var network: WifiNetworkConfig? = null
    private var pending: DataChannelMessages.Request? = null
    private var answered = false
    private var confirmed = false
    private var listening = false
    private var infoSent = false
    private var joined = false
    init { require(generation > 0 && connection > 0 && now >= 0 && deadline > now) }
    fun tick(now: Long): List<Fe35SessionEvent> {
        if (closed) return listOf(Fe35SessionEvent("WIFI_JOIN_FAILED"))
        if (now < last || now >= deadline) return fail()
        last = now
        return emptyList()
    }
    fun ready(g: Long, c: Long, value: WifiNetworkConfig, now: Long): List<Fe35SessionEvent> {
        if (g != generation || c != connection) return fail()
        val expired = tick(now); if (expired.isNotEmpty()) return expired
        if (network != null) return fail()
        network = value
        val request = pending ?: return emptyList()
        pending = null
        return answer(request)
    }
    fun listening(g: Long, c: Long, port: Int, now: Long): List<Fe35SessionEvent> {
        if (g != generation || c != connection) return fail()
        val expired = tick(now); if (expired.isNotEmpty()) return expired
        if (!confirmed || listening) return fail()
        info = checkNotNull(network).connectionInfo(port)
        listening = true
        return listOf(send(33, encodeTlv(1)))
    }
    fun accepted(g: Long, c: Long, now: Long): List<Fe35SessionEvent> {
        if (g != generation || c != connection) return fail()
        val expired = tick(now); if (expired.isNotEmpty()) return expired
        if (!infoSent || joined) return fail()
        joined = true
        return listOf(Fe35SessionEvent("TCP_CONTROL_ACCEPTED"))
    }
    fun resource(payload: ByteArray): List<Fe35SessionEvent> {
        if (closed) return fail()
        val items = Tlv.parseAll(payload)
        // Parse the whole frame before effects.
        val requests = items.map { if (it.tag == 1) DataChannelMessages.parseRequest(it.valueView()) else null }
        val results = items.map { if (it.tag == 7) DataChannelMessages.parseResult(it.valueView()) else null }
        val out = ArrayList<Fe35SessionEvent>()
        for (i in items.indices) when (items[i].tag) {
            1 -> {
                val r = requests[i]!!
                if (r.dataChannel != 3) out += send(4, DataChannelMessages.refusePayload(r.dataChannel, DataChannelRefusal.NO_CHANNEL))
                else if (network == null) {
                    if (pending == null) { pending = r; out += Fe35SessionEvent("WIFI_NETWORK_REQUESTED") }
                } else out += answer(r)
            }
            7 -> {
                val r = results[i]!!
                if (answered && r.dataChannel == 3) {
                    if (r.result != DataChannelMessages.RESULT_OK) return fail()
                    if (!confirmed) {
                        confirmed = true
                        out += Fe35SessionEvent("WIFI_LISTEN")
                    }
                }
            }
            else -> return fail()
        }
        return out
    }
    fun wifi(payload: ByteArray): List<Fe35SessionEvent> {
        if (closed) return fail()
        val items = Tlv.parseAll(payload)
        val macs = items.map {
            if (it.tag != 2) null else {
                val b = it.valueView()
                require(b.all { v -> v.toInt() in 0x20..0x7e })
                val mac = b.decodeToString()
                require(mac == "busy" || Regex("[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}").matches(mac))
                mac
            }
        }
        val out = ArrayList<Fe35SessionEvent>()
        for (i in items.indices) when (items[i].tag) {
            2 -> if (listening && !infoSent && macs[i] != "busy") {
                infoSent = true
                out += send(33, encodeTlv(3, checkNotNull(info).encode().encodeToByteArray()))
                out += Fe35SessionEvent("WIFI_WAIT_TCP")
            }
            5 -> { out += send(33, encodeTlv(6)); out += fail(); return out }
            else -> return fail()
        }
        return out
    }
    private fun answer(r: DataChannelMessages.Request): List<Fe35SessionEvent> {
        val network = checkNotNull(network)
        if (!answered && !r.capability.canUse(network.frequencyMhz))
            return listOf(send(4, DataChannelMessages.refusePayload(3, DataChannelRefusal.NO_CHANNEL))) + fail()
        answered = true
        return listOf(send(4, DataChannelMessages.acceptPayload(3, 1, network.frequencyMhz)))
    }
    fun close() { closed = true; info = null; network = null; pending = null }
    private fun fail(): List<Fe35SessionEvent> { close(); return listOf(Fe35SessionEvent("WIFI_JOIN_FAILED")) }
    override fun toString() = "NearbyWifiJoin(closed=$closed, joined=$joined)"
}
