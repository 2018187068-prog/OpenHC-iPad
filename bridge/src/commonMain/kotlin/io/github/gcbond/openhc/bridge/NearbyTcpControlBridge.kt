package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.nearby.*

/** Preauthenticated WiFi ControlLink and bounded ReceiverSession/DMSDP setup lifecycle.
 * Root material encrypts Nearby frames; the PAKE key stays private for DMSDP CTR.
 * The owner must serialize cancellation and authorize every I/O using its original lease.
 * No timer or detached key creates new authority. */
class NearbyTcpControlBridge(deviceIdText: String, rootKey: ByteArray, constA: ByteArray, constB: ByteArray) {
    private val lock = Fe35ControlBridgeLock()
    private val expectedDeviceId=deviceIdText
    private var receiverConfigured=false
    private val session = Fe35NearbyControlSession(deviceIdText, rootKey, constA, constB,
        Fe35RandomSource(::nearbySecureRandomBytes), wifiControl = true)
    private var key: ByteArray? = null
    private var generation = 0L
    private var connection = 0L
    private var deadline = 0L
    private var last = 0L
    private var started = false
    private var closed = false
    private var detached = false
    private var listenerRequested = false
    private var listenerPort = 0
    private val pending = arrayListOf<Pair<Int,SocketMessages.Request>>()
    private val receiver = NearbyReceiverLifecycle { checkNotNull(key) }

    init { session.wifiSocketRequest = ::socketRequest }

    fun configureReceiver(config: NearbyReceiverDeviceConfig): Boolean = lock.withLock {
        if(started || closed || receiverConfigured || config.deviceId!=expectedDeviceId) return@withLock false
        receiver.configure(config);receiverConfigured=true;true
    }

    fun start(generation: Long, connection: Long, deadlineMillis: Long, nowMillis: Long,
              sessionKey: ByteArray): List<Fe35ControlBridgeEvent> = lock.withLock {
        if (started || closed || generation <= 0 || connection <= 0 || sessionKey.size != 16 ||
            nowMillis < 0 || deadlineMillis <= nowMillis) return@withLock finish("TCP_REJECTED")
        this.generation = generation; this.connection = connection
        deadline = deadlineMillis;last = nowMillis;started = true; key = sessionKey.copyOf()
        try { session.start(nowMillis).map(::Fe35ControlBridgeEvent) }
        catch (_: Exception) { finish("TCP_REJECTED") }
    }

    fun feed(generation: Long, connection: Long, data: ByteArray, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) { check(!detached); session.feed(data) }

    fun tick(generation: Long, connection: Long, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) { session.onTick(nowMillis) + receiver.tick(nowMillis) }

    fun listenerReady(generation: Long, connection: Long, endpoint: Int, port: Int, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) {
            if (endpoint == 2) receiver.listenerReady(port) else {
                check(endpoint == 1 && listenerRequested && listenerPort == 0 && port in 1..65535)
                listenerPort = port
                pending.map { session.answerWifiSocket(it.first,it.second,port) }.also { pending.clear() }
            }
        }
    fun endpointConnected(generation: Long, connection: Long, endpoint: Int, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) { check(listenerPort > 0); receiver.connected(endpoint) }
    fun endpointData(generation: Long, connection: Long, endpoint: Int, data: ByteArray, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) { receiver.feed(endpoint,data,nowMillis) }
    fun endpointClosed(generation: Long, connection: Long, endpoint: Int, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) { receiver.closed(endpoint); emptyList() }
    fun controlClosed(generation: Long, connection: Long, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) { detach() }

    private fun detach(): List<Fe35SessionEvent> {
        check(!detached && listenerPort > 0 && pending.isEmpty() && !session.hasBufferedInput)
        detached = true; session.close()
        return listOf(Fe35SessionEvent("TCP_CONTROL_DETACHED"))
    }
    private fun socketRequest(outer: Int, r: SocketMessages.Request): List<Fe35SessionEvent> {
        if (r.channel != 3 || r.businessId != 20 || !r.tag.contentEquals("DMSDP".encodeToByteArray()) ||
            r.protocol and 1 == 0 || r.uuid != null)
            return listOf(session.answerWifiSocket(outer,r,0), Fe35SessionEvent("SOCKET_REQUEST_REJECTED"))
        if (listenerPort > 0) return listOf(session.answerWifiSocket(outer,r,listenerPort))
        check(pending.size < 8);pending += outer to r
        if (listenerRequested) return emptyList()
        listenerRequested = true
        return listOf(Fe35SessionEvent("DMSDP_LISTEN",channel=1))
    }

    fun close() = lock.withLock { finish("TCP_CLOSED"); Unit }

    private fun invoke(g: Long, c: Long, now: Long, op: () -> List<Fe35SessionEvent>): List<Fe35ControlBridgeEvent> = lock.withLock {
        if (!started || closed || g != generation || c != connection || now < last || now >= deadline)
            return@withLock finish("TCP_REJECTED")
        last = now
        try {
            val events = op().flatMap {
                if (it.kind == "TCP_DISCONNECT" && listenerPort > 0) detach() else listOf(it)
            }
            if (events.any { it.kind in setOf("INPUT_DISCARDED", "OUT_OF_ORDER", "HANDSHAKE_TIMED_OUT") })
                return@withLock finish("TCP_REJECTED")
            val result = events.map(::Fe35ControlBridgeEvent)
            if (events.any { it.kind in setOf("TCP_DISCONNECT","DMSDP_CAPABILITY_REQUIRED",
                    "DMSDP_CONFIG_REQUIRED","DMSDP_HISIGHT_REQUIRED") }) finish("TCP_CLOSED")
            result
        } catch (_: Exception) { finish("TCP_REJECTED") }
    }

    private fun finish(kind: String): List<Fe35ControlBridgeEvent> {
        closed = true; key?.fill(0); key = null; session.close();receiver.close();pending.clear()
        return listOf(Fe35ControlBridgeEvent(Fe35SessionEvent(kind)))
    }
    internal val hasPrivateKey: Boolean get() = key != null
    override fun toString() = "NearbyTcpControlBridge(started=$started, closed=$closed)"
}
