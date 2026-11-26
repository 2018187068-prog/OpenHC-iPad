package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.nearby.Fe35NearbyControlSession
import io.github.gcbond.openhc.core.nearby.Fe35RandomSource
import io.github.gcbond.openhc.core.nearby.Fe35SessionEvent
import io.github.gcbond.openhc.core.nearby.nearbySecureRandomBytes

/** Copy-owning event DTO exported by the iOS framework. Payload bytes are never logged. */
class Fe35ControlBridgeEvent internal constructor(event: Fe35SessionEvent) {
    val kind: String = event.kind
    val channel: Int = event.channel
    val byteCount: Int = event.byteCount
    private val frameBytes = event.frame?.copyOf()
    private val uuidBytes = event.serviceUuid?.copyOf()
    val frame: ByteArray? get() = frameBytes?.copyOf()
    val serviceUuid: ByteArray? get() = uuidBytes?.copyOf()

    override fun toString(): String = "Fe35ControlBridgeEvent($kind, bytes=$byteCount)"
}

/**
 * Serialized, bounded FE35 control-frame API. The caller supplies all key material and must close
 * the bridge when finished. An unexpected session exception closes the session and returns ERROR.
 */
class Fe35ControlBridge private constructor(
    private val session: Fe35NearbyControlSession,
) {
    private val lock = Fe35ControlBridgeLock()
    private var closed = false

    constructor(deviceIdText: String, rootKey: ByteArray, constA: ByteArray, constB: ByteArray) : this(
        createSession(deviceIdText, rootKey, constA, constB, null),
    )

    internal constructor(
        deviceIdText: String,
        rootKey: ByteArray,
        constA: ByteArray,
        constB: ByteArray,
        random: Fe35RandomSource,
    ) : this(createSession(deviceIdText, rootKey, constA, constB, random))

    fun start(nowMillis: Long): List<Fe35ControlBridgeEvent> = invoke { session.start(nowMillis) }

    fun feed(data: ByteArray): List<Fe35ControlBridgeEvent> = invoke {
        if (data.size > MAX_INPUT_BYTES) throw IllegalArgumentException("INPUT_LIMIT")
        session.feed(data.copyOf())
    }

    fun listenerReady(channel: Int): List<Fe35ControlBridgeEvent> =
        invoke { session.onAuthListenerReady(channel) }

    fun tick(nowMillis: Long): List<Fe35ControlBridgeEvent> = invoke { session.onTick(nowMillis) }

    fun close() = lock.withLock {
        if (!closed) {
            closed = true
            session.close()
        }
    }

    override fun toString(): String = "Fe35ControlBridge(closed=$closed)"

    private fun invoke(operation: () -> List<Fe35SessionEvent>): List<Fe35ControlBridgeEvent> = lock.withLock {
        if (closed) return@withLock listOf(Fe35ControlBridgeEvent(Fe35SessionEvent("CLOSED")))
        try {
            operation().map(::Fe35ControlBridgeEvent)
        } catch (e: IllegalArgumentException) {
            session.close()
            closed = true
            listOf(Fe35ControlBridgeEvent(Fe35SessionEvent("ERROR_INVALID_INPUT")))
        } catch (_: Exception) {
            session.close()
            closed = true
            listOf(Fe35ControlBridgeEvent(Fe35SessionEvent("ERROR_SESSION_CLOSED")))
        }
    }

    private companion object {
        const val MAX_KEY_BYTES = 64
        const val MAX_INPUT_BYTES = 64 * 1024

        fun boundedCopy(value: ByteArray, max: Int): ByteArray {
            require(value.isNotEmpty() && value.size <= max) { "KEY_MATERIAL_SIZE_INVALID" }
            return value.copyOf()
        }

        fun createSession(
            deviceIdText: String,
            rootKey: ByteArray,
            constA: ByteArray,
            constB: ByteArray,
            random: Fe35RandomSource?,
        ): Fe35NearbyControlSession {
            require(rootKey.isNotEmpty() && rootKey.size <= MAX_KEY_BYTES &&
                constA.isNotEmpty() && constA.size <= MAX_KEY_BYTES &&
                constB.isNotEmpty() && constB.size <= MAX_KEY_BYTES) { "KEY_MATERIAL_SIZE_INVALID" }
            val root = rootKey.copyOf()
            val a = constA.copyOf()
            val b = constB.copyOf()
            return try {
                if (random == null) Fe35NearbyControlSession(deviceIdText, root, a, b)
                else Fe35NearbyControlSession(deviceIdText, root, a, b, random)
            } finally {
                root.fill(0)
                a.fill(0)
                b.fill(0)
            }
        }
    }
}

internal expect class Fe35ControlBridgeLock() {
    fun <T> withLock(block: () -> T): T
}
