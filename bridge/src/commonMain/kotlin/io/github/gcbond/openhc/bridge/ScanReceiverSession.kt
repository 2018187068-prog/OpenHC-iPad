package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.common.identity.BluetoothAddress
import io.github.gcbond.openhc.core.common.identity.HostIdentity
import io.github.gcbond.openhc.core.nearby.PairingQrCode
import io.github.gcbond.openhc.core.nearby.nearbySecureRandomBytes

/** All inputs are in-memory; the address must be the same local address used by control/auth.
 * lifetimeMillis is a monotonic session budget, not a power lease or permission to enable Bluetooth. */
class ScanReceiverConfig(
    val host: HostIdentity,
    bluetoothAddress: String,
    val supportsUsb: Boolean,
    val lifetimeMillis: Long,
) {
    val bluetoothAddress: String = BluetoothAddress.format(BluetoothAddress.parse(bluetoothAddress))
    init {
        require(this.bluetoothAddress != BluetoothAddress.UNAVAILABLE) { "LOCAL_ADDRESS_UNAVAILABLE" }
        require(lifetimeMillis > 0) { "LIFETIME_INVALID" }
        PairingQrCode.displayName(host.deviceName)
    }
    override fun toString(): String = "ScanReceiverConfig(redacted)"
}

/** QR/PIN are sensitive UI-only values, never diagnostics. A consumer must invalidate previously
 * received values on CLEAR_PAIRING or a generation change; immutable strings cannot be recalled. */
class ScanReceiverEvent internal constructor(
    val kind: String,
    val generation: Long,
    val reason: String = "",
    val qrCode: String? = null,
    val pinCode: String? = null,
) {
    override fun toString(): String = "ScanReceiverEvent($kind, generation=$generation, reason=$reason)"
}

/**
 * Bounded scan-startup model, derived from WirelessReceiverSession.start/onListening and PinCodes
 * in OpenHC 8132399bea6aa86d68da6d3e1d9e3e001c0a7643. No device I/O, key file, UI or power ownership.
 *
 * Call chain: start -> OPEN_CONTROL_LISTENER -> actual RFCOMM + SDP callbacks -> PAIRING_READY.
 * The platform must execute CLOSE_CONTROL_TRANSPORT for all partially opened listeners/CIDs.
 * onControl* callbacks are solely the initial FE35 listener. The existing Fe35ControlBridge's
 * listenerReady is the later FE36/auth callback and must never be routed here.
 * Callers supply one monotonic clock and schedule tick at/before deadlineMillis. All operations
 * are serialized; returned actions must be dispatched in order outside this lock.
 */
class ScanReceiverSession internal constructor(
    private val config: ScanReceiverConfig,
    private val entropy: (Int) -> ByteArray,
) {
    constructor(config: ScanReceiverConfig) : this(config, ::nearbySecureRandomBytes)

    private val lock = Fe35ControlBridgeLock()
    private var currentGeneration = 0L
    private var currentState = "IDLE"
    private var deadline = 0L
    private var lastNow = 0L
    private var pin: String? = null
    private var rfcommChannel: Int? = null
    private var sdpReady = false
    private var handedOff = false

    val generation: Long get() = lock.withLock { currentGeneration }
    val state: String get() = lock.withLock { currentState }
    val deadlineMillis: Long? get() = lock.withLock { if (active()) deadline else null }

    fun start(nowMillis: Long): List<ScanReceiverEvent> = lock.withLock {
        if (active()) return@withLock listOf(event("REJECTED", "ALREADY_ACTIVE"))
        require(nowMillis >= 0 && nowMillis <= Long.MAX_VALUE - config.lifetimeMillis) { "TIME_INVALID" }
        check(currentGeneration < Long.MAX_VALUE) { "GENERATION_EXHAUSTED" }
        currentGeneration++
        currentState = "STARTING"
        deadline = nowMillis + config.lifetimeMillis
        lastNow = nowMillis
        rfcommChannel = null
        sdpReady = false
        handedOff = false
        try {
            pin = ScanPins.next(entropy)
            listOf(event("OPEN_CONTROL_LISTENER"))
        } catch (_: Exception) {
            finish("FAILED", "PIN_ENTROPY_FAILED")
        }
    }

    /** Signal only after actual initial FE35 RFCOMM registration has succeeded. */
    fun onControlRfcommReady(generation: Long, channel: Int, nowMillis: Long): List<ScanReceiverEvent> =
        update(generation, nowMillis) {
            if (channel !in 1..30) return@update finish("FAILED", "CONTROL_CHANNEL_INVALID")
            if (rfcommChannel != null && rfcommChannel != channel)
                return@update finish("FAILED", "CONTROL_READY_CONFLICT")
            if (currentState != "STARTING") return@update emptyList()
            rfcommChannel = channel
            pairingIfReady()
        }

    /** Signal only after actual initial FE35 SDP service registration has succeeded. */
    fun onControlSdpReady(generation: Long, nowMillis: Long): List<ScanReceiverEvent> =
        update(generation, nowMillis) {
            if (currentState != "STARTING") return@update emptyList()
            sdpReady = true
            pairingIfReady()
        }

    fun onControlAccepted(generation: Long, nowMillis: Long): List<ScanReceiverEvent> =
        update(generation, nowMillis) {
            if (currentState == "CONNECTED") return@update emptyList()
            if (currentState != "WAITING_FOR_SCAN") return@update finish("FAILED", "CONTROL_ACCEPT_OUT_OF_ORDER")
            currentState = "CONNECTED"
            listOf(event("CLEAR_PAIRING"), event("CONTROL_CONNECTED"))
        }

    fun onControlFailure(generation: Long, nowMillis: Long): List<ScanReceiverEvent> =
        update(generation, nowMillis) { finish("FAILED", "CONTROL_TRANSPORT_FAILED") }

    fun tick(generation: Long, nowMillis: Long): List<ScanReceiverEvent> =
        update(generation, nowMillis) { emptyList() }

    /** Native transport boundary, solely for the initial FE35 listener. Every callback
     * carries the generation captured before registration; late callbacks cannot revive it.
     * CLEANED marks the platform worker teardown tail and terminates a still-active
     * session. It does not confirm remote cleanup or authorize lease recovery;
     * the native caller must inspect its separate typed completion after return. */
    fun onTransportEvent(generation: Long, kind: String, channel: Int, nowMillis: Long): List<ScanReceiverEvent> =
        when (kind) {
            "RFCOMM_READY" -> onControlRfcommReady(generation, channel, nowMillis)
            "SDP_READY" -> onControlSdpReady(generation, nowMillis)
            "ACCEPTED" -> onControlAccepted(generation, nowMillis)
            "TICK" -> tick(generation, nowMillis)
            "STOP", "CLEANED" -> stop(generation)
            else -> onControlFailure(generation, nowMillis)
        }

    /** Stop is clock-independent and idempotent, including during partial listener startup. */
    fun stop(generation: Long): List<ScanReceiverEvent> = lock.withLock {
        if (generation != currentGeneration || !active()) emptyList() else finish("STOPPED", "STOP_REQUESTED")
    }

    /** One-shot, same PIN as PAIRING_READY; this is not an authentication result.
     * Expired handoff requests return cleanup events, never a PIN. */
    fun takeAuthHandoff(generation: Long, nowMillis: Long): List<ScanReceiverEvent> =
        update(generation, nowMillis) {
            if (currentState != "CONNECTED" || handedOff) return@update emptyList()
            handedOff = true
            listOf(ScanReceiverEvent("AUTH_HANDOFF", currentGeneration, pinCode = checkNotNull(pin)))
        }

    override fun toString(): String = lock.withLock { "ScanReceiverSession(state=$currentState, generation=$currentGeneration)" }

    private fun active(): Boolean = currentState == "STARTING" || currentState == "WAITING_FOR_SCAN" || currentState == "CONNECTED"

    private fun event(kind: String, reason: String = "") = ScanReceiverEvent(kind, currentGeneration, reason)

    private fun pairingIfReady(): List<ScanReceiverEvent> {
        if (rfcommChannel == null || !sdpReady) return emptyList()
        val currentPin = checkNotNull(pin)
        val qr = PairingQrCode.build(config.host, config.bluetoothAddress, currentPin, config.supportsUsb)
        currentState = "WAITING_FOR_SCAN"
        return listOf(ScanReceiverEvent("PAIRING_READY", currentGeneration, qrCode = qr, pinCode = currentPin))
    }

    private fun update(generation: Long, nowMillis: Long, operation: () -> List<ScanReceiverEvent>): List<ScanReceiverEvent> = lock.withLock {
        if (generation != currentGeneration || !active()) return@withLock emptyList()
        if (nowMillis < lastNow) return@withLock finish("FAILED", "CLOCK_REVERSED")
        lastNow = nowMillis
        if (nowMillis >= deadline) return@withLock finish("STOPPED", "DEADLINE_EXPIRED")
        operation()
    }

    private fun finish(state: String, reason: String): List<ScanReceiverEvent> {
        currentState = state
        pin = null
        rfcommChannel = null
        sdpReady = false
        handedOff = false
        return listOf(event("CLEAR_PAIRING"), event("CLOSE_CONTROL_TRANSPORT"), event(state, reason))
    }
}

internal object ScanPins {
    // A uniform 20-bit sample has 1,048,576 outcomes. Reject >=1,000,000, never biased modulo.
    // Bounded attempts fail closed if an entropy provider is broken; all temporary bytes are wiped.
    fun next(entropy: (Int) -> ByteArray): String {
        repeat(128) {
            val bytes = entropy(3)
            val value = try {
                check(bytes.size == 3) { "PIN_ENTROPY_SIZE" }
                ((bytes[0].toInt() and 15) shl 16) or
                    ((bytes[1].toInt() and 255) shl 8) or (bytes[2].toInt() and 255)
            } finally { bytes.fill(0) }
            if (value < 1_000_000) return value.toString().padStart(6, '0')
        }
        error("PIN_ENTROPY_REJECTED")
    }
}
