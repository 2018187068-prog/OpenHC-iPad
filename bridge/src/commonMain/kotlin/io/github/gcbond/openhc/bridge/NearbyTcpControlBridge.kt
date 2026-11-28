package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.nearby.*

/** Internal preauthenticated WiFi ControlLink subset, not a media ReceiverSession.
 * Root material encrypts Nearby frames; the PAKE key stays private for the future DMSDP join.
 * The owner must serialize cancellation and authorize every I/O using its original lease.
 * No timer or detached key creates new authority. */
class NearbyTcpControlBridge(deviceIdText: String, rootKey: ByteArray, constA: ByteArray, constB: ByteArray) {
    private val lock = Fe35ControlBridgeLock()
    private val session = Fe35NearbyControlSession(deviceIdText, rootKey, constA, constB,
        Fe35RandomSource(::nearbySecureRandomBytes), wifiControl = true)
    private var key: ByteArray? = null
    private var generation = 0L
    private var connection = 0L
    private var deadline = 0L
    private var last = 0L
    private var started = false
    private var closed = false

    fun start(generation: Long, connection: Long, deadlineMillis: Long, nowMillis: Long,
              sessionKey: ByteArray): List<Fe35ControlBridgeEvent> = lock.withLock {
        if (started || closed || generation <= 0 || connection <= 0 || sessionKey.size != 16 ||
            nowMillis < 0 || deadlineMillis <= nowMillis) return@withLock finish("TCP_REJECTED")
        this.generation = generation; this.connection = connection
        deadline = deadlineMillis; last = nowMillis; started = true; key = sessionKey.copyOf()
        try { session.start(nowMillis).map(::Fe35ControlBridgeEvent) }
        catch (_: Exception) { finish("TCP_REJECTED") }
    }

    fun feed(generation: Long, connection: Long, data: ByteArray, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) { session.feed(data) }

    fun tick(generation: Long, connection: Long, nowMillis: Long): List<Fe35ControlBridgeEvent> =
        invoke(generation, connection, nowMillis) { session.onTick(nowMillis) }

    fun close() = lock.withLock { finish("TCP_CLOSED"); Unit }

    private fun invoke(g: Long, c: Long, now: Long, op: () -> List<Fe35SessionEvent>): List<Fe35ControlBridgeEvent> = lock.withLock {
        if (!started || closed || g != generation || c != connection || now < last || now >= deadline)
            return@withLock finish("TCP_REJECTED")
        last = now
        try {
            val events = op()
            if (events.any { it.kind in setOf("INPUT_DISCARDED", "OUT_OF_ORDER", "HANDSHAKE_TIMED_OUT") })
                return@withLock finish("TCP_REJECTED")
            val result = events.map(::Fe35ControlBridgeEvent)
            if (events.any { it.kind == "TCP_DISCONNECT" }) finish("TCP_CLOSED")
            result
        } catch (_: Exception) { finish("TCP_REJECTED") }
    }

    private fun finish(kind: String): List<Fe35ControlBridgeEvent> {
        closed = true; key?.fill(0); key = null; session.close()
        return listOf(Fe35ControlBridgeEvent(Fe35SessionEvent(kind)))
    }
    internal val hasPrivateKey: Boolean get() = key != null
    override fun toString() = "NearbyTcpControlBridge(started=$started, closed=$closed)"
}
