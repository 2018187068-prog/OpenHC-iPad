package io.github.gcbond.openhc.core.nearby

import io.github.gcbond.openhc.core.common.ByteReader
import io.github.gcbond.openhc.core.common.ByteWriter

/** Safe-to-inspect callback from the FE35 control session; data fields are only frames or service UUIDs. */
class Fe35SessionEvent internal constructor(
    val kind: String,
    frame: ByteArray? = null,
    serviceUuid: ByteArray? = null,
    val byteCount: Int = 0,
    val channel: Int = 0,
) {
    private val frameBytes = frame?.copyOf()
    private val uuidBytes = serviceUuid?.copyOf()
    val frame: ByteArray? get() = frameBytes?.copyOf()
    val serviceUuid: ByteArray? get() = uuidBytes?.copyOf()
    override fun toString(): String = "Fe35SessionEvent($kind, bytes=$byteCount)"
}

internal fun interface Fe35RandomSource { fun nextBytes(size: Int): ByteArray }

/**
 * Bounded FE35 Bluetooth control-frame session. It ports the pinned Nearby frame/handshake flow and
 * delegates command 3/4 semantics to [Fe35ControlNegotiator]. Calls for one session must be serialized.
 */
class Fe35NearbyControlSession internal constructor(
    deviceIdText: String,
    rootKey: ByteArray,
    constA: ByteArray,
    constB: ByteArray,
    private val random: Fe35RandomSource,
    private val wifiControl: Boolean = false,
) {
    constructor(deviceIdText: String, rootKey: ByteArray, constA: ByteArray, constB: ByteArray) :
        this(deviceIdText, rootKey, constA, constB, Fe35RandomSource(::nearbySecureRandomBytes))

    private val deviceId = deviceIdText.encodeToByteArray()
    private val cipher = NearbyFrameCipher(rootKey, constA, constB)
    private val decoder = NearbyFrameDecoder(MAX_FRAME_PAYLOAD)
    private val negotiator = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
    private var started = false
    private var closed = false
    private var encrypted = false
    private var seen = 0
    private var handshakeDeadline: Long? = null
    private var wifi: NearbyWifiJoin? = null
    internal var wifiSocketRequest: ((Int, SocketMessages.Request) -> List<Fe35SessionEvent>)? = null
    internal fun answerWifiSocket(outer: Int, request: SocketMessages.Request, port: Int): Fe35SessionEvent =
        sendFrame(outer, SocketMessages.responsePayload(if (port > 0) 0 else 1, port,
            request.channel, request.businessId, request.tag, if (port > 0) 1 else 0))

    /** Trusted internal continuation, called only after real authentication and auth-CID cleanup.
     * Uses the captured original owner/common absolute deadline; never starts another budget. */
    fun authenticated(generation: Long, connection: Long, deadline: Long, now: Long): List<Fe35SessionEvent> {
        check(isHandshakeComplete && wifi == null)
        wifi = NearbyWifiJoin(generation, connection, deadline, now, ::sendFrame)
        return emptyList()
    }
    fun networkReady(g: Long, c: Long, info: WifiNetworkConfig, now: Long): List<Fe35SessionEvent> =
        checkNotNull(wifi).ready(g, c, info, now)
    fun wifiListening(g: Long, c: Long, port: Int, now: Long): List<Fe35SessionEvent> =
        checkNotNull(wifi).listening(g, c, port, now)
    fun tcpAccepted(g: Long, c: Long, now: Long): List<Fe35SessionEvent> =
        checkNotNull(wifi).accepted(g, c, now)

    init {
        require(deviceIdText.isNotEmpty() && deviceIdText.length <= MAX_DEVICE_ID_TEXT) { "DEVICE_ID_TEXT_INVALID" }
    }

    val isHandshakeComplete: Boolean get() = seen == SEEN_ALL && !closed
    internal val hasBufferedInput: Boolean get() = decoder.buffered > 0
    val nextTickAtMillis: Long? get() = handshakeDeadline

    /** Emits the pinned upstream connectId frame and arms its five-second handshake deadline. */
    fun start(nowMillis: Long): List<Fe35SessionEvent> {
        check(!started && !closed) { "FE35_SESSION_START_OUT_OF_ORDER" }
        started = true
        handshakeDeadline = nowMillis + HANDSHAKE_TIMEOUT_MS
        val raw = randomBytes(4)
        val span = (CONNECT_ID_MAX - CONNECT_ID_MIN + 1).toLong()
        val connectId = (CONNECT_ID_MIN + ByteReader(raw).u32Be() % span).toInt()
        raw.fill(0)
        val payload = ByteWriter().tlv(ChannelManagement.TAG_CONNECT_ID, ChannelManagement.connectIdValue(connectId)).toByteArray()
        val out = arrayListOf(sendFrame(ChannelManagement.OUTER_TYPE, payload))
        if (wifiControl) out += sendFrame(ChannelManagement.OUTER_TYPE, ByteWriter()
            .tlv(ChannelManagement.TAG_VERSION_REQUEST, byteArrayOf(2))
            .tlv(ChannelManagement.TAG_SUMMARY_REQUEST, deviceId)
            .tlv(ChannelManagement.TAG_ENCRYPTION_REQUEST, byteArrayOf(1)).toByteArray())
        return out
    }

    /** Feeds a bounded stream chunk; fragments and coalesced frames follow NearbyFrameDecoder semantics. */
    fun feed(data: ByteArray): List<Fe35SessionEvent> {
        if (!started) return listOf(Fe35SessionEvent("OUT_OF_ORDER"))
        if (closed || data.isEmpty()) return emptyList()
        if (data.size > MAX_INPUT_CHUNK || decoder.buffered + data.size > MAX_BUFFERED_BYTES) {
            val discarded = decoder.buffered + data.size
            decoder.clear()
            return listOf(Fe35SessionEvent("INPUT_DISCARDED", byteCount = discarded))
        }
        val out = ArrayList<Fe35SessionEvent>()
        try {
            decoder.feed(data)
        } catch (_: Exception) {
            decoder.clear()
            return listOf(Fe35SessionEvent("INPUT_DISCARDED", byteCount = data.size))
        }
        while (true) {
            val pending = decoder.buffered
            val frame = try {
                decoder.next()
            } catch (_: Exception) {
                out += Fe35SessionEvent("INPUT_DISCARDED", byteCount = pending)
                null
            } ?: break
            try {
                out += process(frame)
            } catch (_: Exception) {
                if (wifi != null) { close(); return listOf(Fe35SessionEvent("WIFI_JOIN_FAILED")) }
                out += Fe35SessionEvent("INPUT_DISCARDED", byteCount = frame.payloadView().size)
            }
        }
        return out
    }

    /** Completes the platform RFCOMM listener callback and sends the full encrypted command-4 frame. */
    fun onAuthListenerReady(channel: Int): List<Fe35SessionEvent> {
        if (closed || !isHandshakeComplete) return listOf(Fe35SessionEvent("OUT_OF_ORDER"))
        return emitNegotiatorActions(negotiator.onAuthListenerReady(channel))
    }

    /** The accepted auth connection may be reported to close any future duplicate requests. */
    fun onAuthConnected() {
        check(!closed) { "FE35_SESSION_CLOSED" }
        negotiator.onAuthConnected()
    }

    fun onTick(nowMillis: Long): List<Fe35SessionEvent> {
        wifi?.let { return it.tick(nowMillis) }
        val deadline = handshakeDeadline ?: return emptyList()
        if (nowMillis < deadline || closed) return emptyList()
        close()
        return listOf(Fe35SessionEvent("HANDSHAKE_TIMED_OUT"))
    }

    fun close() {
        if (closed) return
        closed = true
        handshakeDeadline = null
        decoder.clear()
        negotiator.close()
        cipher.close()
        wifi?.close()
        wifi = null
        deviceId.fill(0)
    }

    override fun toString(): String =
        "Fe35NearbyControlSession(handshake=$isHandshakeComplete, encrypted=$encrypted, closed=$closed)"

    private fun process(frame: NearbyFrame): List<Fe35SessionEvent> {
        if (wifiControl) {
            val payload = cipher.open(frame)
            return when (frame.outerType) {
                ChannelManagement.OUTER_TYPE -> handleHandshake(payload)
                SocketMessages.OUTER_TYPE_MESSAGE, SocketMessages.OUTER_TYPE_RESOURCE -> {
                    require(isHandshakeComplete && encrypted && frame.isEncrypted)
                    val requests = Tlv.parseAll(payload).map {
                        require(it.tag == SocketMessages.CMD_CREATE_REQUEST)
                        SocketMessages.parseRequest(it.valueView())
                    }
                    requests.flatMap { r -> wifiSocketRequest?.invoke(frame.outerType, r) ?:
                        listOf(answerWifiSocket(frame.outerType, r, 0), Fe35SessionEvent("SOCKET_REQUEST_REJECTED")) }
                }
                33 -> {
                    val items = Tlv.parseAll(payload)
                    require(isHandshakeComplete && items.size == 1 && items[0].tag == 5 && items[0].valueView().isEmpty())
                    listOf(sendFrame(33, encodeTlv(6)), Fe35SessionEvent("TCP_DISCONNECT"))
                }
                else -> listOf(Fe35SessionEvent("IGNORED_FRAME"))
            }
        }
        if (wifi != null && (frame.outerType == ChannelManagement.OUTER_TYPE ||
                frame.outerType == SocketMessages.OUTER_TYPE_MESSAGE)) {
            close()
            return listOf(Fe35SessionEvent("WIFI_JOIN_FAILED"))
        }
        val payload = cipher.open(frame)
        return when (frame.outerType) {
            ChannelManagement.OUTER_TYPE -> handleHandshake(payload)
            SocketMessages.OUTER_TYPE_MESSAGE -> handleMessageLayer(payload)
            SocketMessages.OUTER_TYPE_RESOURCE -> wifi?.resource(payload) ?: rejectDataChannel(payload)
            33 -> wifi?.wifi(payload) ?: listOf(Fe35SessionEvent("WIFI_JOIN_FAILED"))
            else -> listOf(Fe35SessionEvent("IGNORED_FRAME"))
        }
    }

    private fun rejectDataChannel(payload: ByteArray): List<Fe35SessionEvent> =
        Tlv.parseAll(payload).map {
            require(it.tag == DataChannelMessages.CMD_REQUEST)
            val r = DataChannelMessages.parseRequest(it.valueView())
            sendFrame(4, DataChannelMessages.refusePayload(r.dataChannel, DataChannelRefusal.BUSY))
        }

    private fun handleHandshake(payload: ByteArray): List<Fe35SessionEvent> {
        val items = ChannelManagement.decode(payload)
        val replies = ByteWriter()
        for (item in items) {
            when (item) {
                is ChannelManagement.Item.Version -> {
                    seen = seen or SEEN_VERSION
                    if (item.request) replies.tlv(ChannelManagement.TAG_VERSION_RESPONSE, byteArrayOf(ChannelManagement.LOCAL_VERSION.toByte()))
                }
                is ChannelManagement.Item.Summary -> {
                    seen = seen or SEEN_SUMMARY
                    if (item.request) replies.tlv(ChannelManagement.TAG_SUMMARY_RESPONSE, deviceId)
                }
                is ChannelManagement.Item.Encryption -> {
                    encrypted = item.enabled
                    seen = seen or SEEN_ENCRYPTION
                    if (item.request) replies.tlv(ChannelManagement.TAG_ENCRYPTION_RESPONSE, byteArrayOf(if (item.enabled) 1 else 0))
                }
                is ChannelManagement.Item.BluetoothAddress,
                is ChannelManagement.Item.ConnectId,
                is ChannelManagement.Item.Unknown -> Unit
            }
        }
        val out = ArrayList<Fe35SessionEvent>(2)
        if (replies.size > 0) out += sendFrame(ChannelManagement.OUTER_TYPE, replies.toByteArray())
        if (seen == SEEN_ALL && handshakeDeadline != null) {
            handshakeDeadline = null
            out += Fe35SessionEvent("HANDSHAKE_COMPLETED")
        }
        return out
    }

    private fun handleMessageLayer(payload: ByteArray): List<Fe35SessionEvent> {
        val tlvs = Tlv.parseAll(payload)
        if (!isHandshakeComplete) {
            val out = ArrayList<Fe35SessionEvent>()
            for (item in tlvs) {
                if (item.tag != SocketMessages.CMD_CREATE_REQUEST) continue
                val request = SocketMessages.parseRequest(item.valueView())
                val channel = if (request.channel == 0) CHANNEL_BLUETOOTH else request.channel
                val reject = SocketMessages.responsePayload(SocketMessages.STATUS_REJECTED, 0, channel,
                    request.businessId, request.tag, 0)
                out += sendFrame(SocketMessages.OUTER_TYPE_MESSAGE, reject)
                out += Fe35SessionEvent("SOCKET_REQUEST_REJECTED")
            }
            return out
        }
        return emitNegotiatorActions(negotiator.onMessageLayerPayload(payload))
    }

    private fun emitNegotiatorActions(actions: List<Fe35ControlNegotiator.Action>): List<Fe35SessionEvent> {
        val out = ArrayList<Fe35SessionEvent>(actions.size)
        for (action in actions) {
            when (action) {
                is Fe35ControlNegotiator.Action.OpenAuthListener ->
                    out += Fe35SessionEvent("OPEN_AUTH_LISTENER", serviceUuid = action.uuid)
                is Fe35ControlNegotiator.Action.SendControl -> out += sendFrame(SocketMessages.OUTER_TYPE_MESSAGE, action.payload)
                is Fe35ControlNegotiator.Action.ConnectAuthChannel ->
                    out += Fe35SessionEvent("CONNECT_AUTH_CHANNEL", serviceUuid = action.uuid, channel = action.channel)
                Fe35ControlNegotiator.Action.Ignored -> out += Fe35SessionEvent("IGNORED")
                Fe35ControlNegotiator.Action.Discarded -> out += Fe35SessionEvent("INPUT_DISCARDED")
                Fe35ControlNegotiator.Action.Rejected -> out += Fe35SessionEvent("AUTH_CHANNEL_REJECTED")
                Fe35ControlNegotiator.Action.CloseAuthListener -> out += Fe35SessionEvent("CLOSE_AUTH_LISTENER")
                Fe35ControlNegotiator.Action.AbortControl -> {
                    close()
                    out += Fe35SessionEvent("CONTROL_ABORTED")
                }
            }
        }
        return out
    }

    private fun sendFrame(outerType: Int, payload: ByteArray): Fe35SessionEvent {
        require(payload.size <= MAX_FRAME_PAYLOAD) { "FRAME_PAYLOAD_LIMIT" }
        val frame = if (encrypted) {
            val seed = randomBytes(NearbyFrame.SEED_LENGTH)
            try { cipher.seal(outerType, payload, seed).encode() } finally { seed.fill(0) }
        } else NearbyFrame.plain(outerType, payload).encode()
        return Fe35SessionEvent("SEND_FRAME", frame = frame, byteCount = frame.size)
    }

    private fun randomBytes(size: Int): ByteArray {
        val bytes = random.nextBytes(size)
        check(bytes.size == size) { "RANDOM_SOURCE_LENGTH_INVALID" }
        return bytes
    }

    private companion object {
        const val CHANNEL_BLUETOOTH = 2
        const val CONNECT_ID_MIN = 100_000
        const val CONNECT_ID_MAX = 999_999
        const val MAX_DEVICE_ID_TEXT = 128
        const val MAX_FRAME_PAYLOAD = 64 * 1024
        const val MAX_INPUT_CHUNK = 64 * 1024
        const val MAX_BUFFERED_BYTES = MAX_FRAME_PAYLOAD + 512
        const val HANDSHAKE_TIMEOUT_MS = 5_000L
        const val SEEN_VERSION = 1
        const val SEEN_SUMMARY = 2
        const val SEEN_ENCRYPTION = 4
        const val SEEN_ALL = SEEN_VERSION or SEEN_SUMMARY or SEEN_ENCRYPTION
    }
}
