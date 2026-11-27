package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.bridge.hicarauth.*

/** In-memory config from a future trusted owner; no identity/persistence/network loader. */
class Fe36AuthConfig(
    val service: AuthServiceIdentity,
    val selfAuthId: String,
    val envelopeVersion: String,
    deviceInfo: Map<String, String>,
) {
    internal val deviceInfo = deviceInfo.toMap()
    init {
        AccessoryAuthConfig.requireAuthId(selfAuthId, "selfAuthId")
        require(envelopeVersion.length in 1..128)
        require(deviceInfo.size <= 32 && deviceInfo.all { it.key.length <= 128 && it.value.length <= 256 })
    }
    override fun toString() = "Fe36AuthConfig(redacted)"
}

/** SEND bytes are transport-only and copied. No PIN/peer/key appears in diagnostics. */
class Fe36AuthAction internal constructor(val kind: String, val generation: Long, val reason: String = "", bytes: ByteArray? = null) {
    private val payload = bytes?.copyOf()
    val bytes: ByteArray? get() = payload?.copyOf()
    override fun toString() = "Fe36AuthAction($kind,generation=$generation,reason=$reason)"
}

/** Serialized bounded FE36 protocol coordinator, not a listener or caller authorization.
 * Owner passes its original one-shot common AUTH_HANDOFF and immutable absolute
 * deadline, then a single captured connection incarnation. Effects run outside lock.
 * No deployed provider is wired to this class in this slice. */
class Fe36AuthSessionBridge internal constructor(
    private val config: Fe36AuthConfig,
    private val trust: TrustStore,
    private val random: AuthRandom,
) {
    constructor(config: Fe36AuthConfig, trust: TrustStore) : this(config, trust, PlatformAuthRandom)
    private val lock = Fe35ControlBridgeLock()
    private var generation = 0L
    private var connection = 0L
    private var consumed = false
    private var deadline = 0L
    private var lastNow = 0L
    private var total = 0
    private var session: HiCarAuthSession? = null
    private var done = false
    private var closed = false
    private var key: ByteArray? = null

    /** Only the common session can mint this event in Kotlin. This is not a wire API. */
    fun handoff(event: ScanReceiverEvent, nowMillis: Long, deadlineMillis: Long): List<Fe36AuthAction> = lock.withLock {
        if (consumed) return@withLock emptyList()
        consumed = true; generation = event.generation; lastNow = nowMillis; deadline = deadlineMillis
        if (event.kind != "AUTH_HANDOFF" || generation <= 0 || event.pinCode?.let(PinCodes::isValid) != true ||
            nowMillis < 0 || deadlineMillis <= nowMillis || deadlineMillis - nowMillis > 240000)
            return@withLock fail("HANDOFF_INVALID")
        try {
            val authConfig = HiCarAuthConfig(config.service, config.selfAuthId, config.envelopeVersion, event.pinCode, false)
            session = HiCarAuthSession(authConfig, KotlinAccessoryAuthenticator.factory(trust, random), random) { config.deviceInfo }
            listOf(action("OPEN_AUTH_CONNECTION"))
        } catch (_: Exception) { fail("AUTH_INIT_FAILED") }
    }

    /** Connection IDs are assigned by a serialized platform adapter, never by peer bytes. */
    fun connected(generation: Long, connection: Long, nowMillis: Long): List<Fe36AuthAction> = lock.withLock {
        if (!current(generation)) return@withLock emptyList()
        timeFailure(nowMillis)?.let { return@withLock it }
        if (this.connection != 0L || connection <= 0) return@withLock fail("CONNECTION_REUSED")
        this.connection = connection
        emptyList()
    }

    fun receive(generation: Long, connection: Long, bytes: ByteArray, nowMillis: Long): List<Fe36AuthAction> = lock.withLock {
        if (!current(generation)) return@withLock emptyList()
        timeFailure(nowMillis)?.let { return@withLock it }
        if (connection <= 0 || connection != this.connection) return@withLock fail("CONNECTION_MISMATCH")
        if (bytes.isEmpty() || bytes.size > 4096 || total > 65536 - bytes.size) return@withLock fail("AUTH_INPUT_LIMIT")
        total += bytes.size
        val copy = bytes.copyOf()
        try {
            val actions = checkNotNull(session).feed(copy)
            val output = ArrayList<Fe36AuthAction>()
            for (a in actions) when (a) {
                is HiCarAuthAction.Send -> output.add(action("SEND", bytes = a.bytes))
                is HiCarAuthAction.Succeeded -> {
                    if (a.sessionKey.size != 16) return@withLock fail("AUTH_KEY_INVALID")
                    key = a.sessionKey.copyOf(); a.sessionKey.fill(0); done = true
                    session?.cancel(); session = null
                    output.add(action("AUTHENTICATED"))
                }
                is HiCarAuthAction.Failed -> { output.addAll(fail("AUTH_REJECTED")) }
                is HiCarAuthAction.HandshakeAnswered, is HiCarAuthAction.Note -> Unit
            }
            output
        } catch (_: Exception) { fail("AUTH_PROTOCOL_FAILED") }
        finally { copy.fill(0) }
    }

    fun tick(generation: Long, nowMillis: Long): List<Fe36AuthAction> = lock.withLock {
        if (!live(generation)) emptyList() else timeFailure(nowMillis) ?: emptyList()
    }
    fun stop(generation: Long): List<Fe36AuthAction> = lock.withLock {
        if (!live(generation)) emptyList() else fail("STOPPED")
    }
    fun disconnected(generation: Long, connection: Long): List<Fe36AuthAction> = lock.withLock {
        if (!live(generation) || connection != this.connection) emptyList() else fail("DISCONNECTED")
    }
    /** Secret key is copied once to the next trusted protocol stage, never an event/log.
     * Null requires closing the candidate next-stage connection; no usable key escapes
     * after cancellation, expiry, clock reversal or a wrong connection incarnation. */
    fun takeSessionKey(generation: Long, connection: Long, nowMillis: Long): ByteArray? = lock.withLock {
        if (!live(generation) || !done || connection != this.connection) null
        else if (timeFailure(nowMillis) != null) null
        else key?.copyOf().also { key?.fill(0); key = null }
    }
    private fun live(g: Long) = consumed && !closed && g == generation
    private fun current(g: Long) = consumed && !done && g == generation && session != null
    private fun timeFailure(now: Long): List<Fe36AuthAction>? {
        if (now < lastNow) return fail("CLOCK_REVERSED")
        lastNow = now
        return if (now >= deadline) fail("DEADLINE_EXPIRED") else null
    }
    private fun fail(reason: String): List<Fe36AuthAction> {
        if (closed) return emptyList()
        val authenticated = done
        session?.cancel(); session = null; key?.fill(0); key = null; done = true
        closed = true
        return if (authenticated) listOf(action("CLOSE", reason))
            else listOf(action("FAILED", reason), action("CLOSE", reason))
    }
    private fun action(kind: String, reason: String = "", bytes: ByteArray? = null) = Fe36AuthAction(kind, generation, reason, bytes)
    override fun toString() = "Fe36AuthSessionBridge(redacted)"
}
