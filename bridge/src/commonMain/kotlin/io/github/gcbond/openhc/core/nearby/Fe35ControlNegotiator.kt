package io.github.gcbond.openhc.core.nearby

/**
 * Metadata-only FE35 socket negotiation over an already decoded Nearby message-layer payload.
 * It does not parse/encrypt Nearby frames or read/write RFCOMM data.
 */
class Fe35ControlNegotiator(private val mode: Mode) {
    enum class Mode { PASSIVE, RECONNECT }

    sealed class Action {
        class OpenAuthListener(uuid: ByteArray) : Action() {
            private val value = uuid.copyOf()
            val uuid: ByteArray get() = value.copyOf()
        }

        class SendControl(payload: ByteArray) : Action() {
            private val value = payload.copyOf()
            val payload: ByteArray get() = value.copyOf()
        }

        class ConnectAuthChannel(val channel: Int, uuid: ByteArray) : Action() {
            private val value = uuid.copyOf()
            val uuid: ByteArray get() = value.copyOf()
        }

        data object Ignored : Action()
        data object Rejected : Action()
        data object CloseAuthListener : Action()
        data object AbortControl : Action()
    }

    private enum class State { READY, LISTENING, LISTENING_OPEN, WAITING_RESPONSE, CONNECTING, COMPLETE, FAILED }

    private data class Request(val channel: Int, val business: Int, val tag: ByteArray, val protocol: Int, val uuid: ByteArray?)
    private data class Response(val status: Int, val port: Int, val channel: Int, val business: Int,
                                val tag: ByteArray, val protocol: Int, val uuid: ByteArray?)

    private var state = State.READY
    private val pending = ArrayList<Request>(MAX_PENDING)
    private var localChannel = 0
    private var reconnectTag: ByteArray? = null

    /** Starts reconnect negotiation; the tag is retained only to correlate the response. */
    fun requestAuthChannel(tag: ByteArray): Action.SendControl {
        check(mode == Mode.RECONNECT && state == State.READY) { "AUTH_REQUEST_OUT_OF_ORDER" }
        require(tag.isNotEmpty()) { "AUTH_TAG_EMPTY" }
        reconnectTag = tag.copyOf()
        state = State.WAITING_RESPONSE
        return Action.SendControl(encodeTlv(CMD_CREATE_REQUEST, encodeRequest(CHANNEL_BLUETOOTH, BUSINESS_AUTH, tag, 0, null)))
    }

    /** Accepts a decrypted command-3/4 TLV value; unknown or malformed shapes fail closed. */
    fun onMessageLayerPayload(payload: ByteArray): List<Action> {
        check(state != State.FAILED) { "CONTROL_NEGOTIATION_CLOSED" }
        return try {
            val tlv = parseSingleTlv(payload)
            when (tlv.first) {
                CMD_CREATE_REQUEST -> onRequest(parseRequest(tlv.second))
                CMD_CREATE_RESPONSE -> onResponse(parseResponse(tlv.second))
                else -> listOf(Action.Ignored)
            }
        } catch (_: RuntimeException) {
            val closeListener = state == State.LISTENING || state == State.LISTENING_OPEN
            state = State.FAILED
            pending.clear()
            reconnectTag = null
            return if (closeListener) listOf(Action.CloseAuthListener, Action.AbortControl)
            else listOf(Action.AbortControl)
        }
    }

    /** Completes the local listener callback; duplicate/late callbacks are rejected. */
    fun onAuthListenerReady(channel: Int): List<Action> {
        check(mode == Mode.PASSIVE && state == State.LISTENING) { "LISTENER_CALLBACK_OUT_OF_ORDER" }
        if (channel !in 1..MAX_RFCOMM_CHANNEL) {
            state = State.FAILED
            val rejected = pending.map { response(it, STATUS_REJECTED, 0, null) }
            pending.clear()
            return rejected + listOf(Action.CloseAuthListener, Action.AbortControl)
        }
        localChannel = channel
        state = State.LISTENING_OPEN
        val result = pending.map { response(it, STATUS_ACCEPTED, channel, serviceUuid(it.uuid)) }
        pending.clear()
        return result
    }

    /** The passive auth connection is now established; further auth requests are rejected. */
    fun onAuthConnected() {
        check(mode == Mode.PASSIVE && state == State.LISTENING_OPEN) { "AUTH_CONNECT_OUT_OF_ORDER" }
        state = State.COMPLETE
    }

    private fun onRequest(request: Request): List<Action> {
        if (mode != Mode.PASSIVE) return listOf(Action.Ignored)
        if (state != State.READY && state != State.LISTENING && state != State.LISTENING_OPEN) {
            return reject(request)
        }
        if (request.business != BUSINESS_AUTH || request.protocol and PROTOCOL_TCP != 0 ||
            (request.uuid != null && request.uuid.size != UUID_BYTES)) return reject(request)

        val normalized = if (request.channel == 0) CHANNEL_BLUETOOTH else request.channel
        val acceptedRequest = request.copy(channel = normalized)
        return when (state) {
            State.READY -> {
                state = State.LISTENING
                pending += acceptedRequest
                listOf(Action.OpenAuthListener(serviceUuid(request.uuid)))
            }
            State.LISTENING -> {
                if (pending.size >= MAX_PENDING) reject(request)
                else { pending += acceptedRequest; listOf(Action.Ignored) }
            }
            State.LISTENING_OPEN -> listOf(response(acceptedRequest, STATUS_ACCEPTED, localChannel, serviceUuid(request.uuid)))
            else -> reject(request)
        }
    }

    private fun onResponse(response: Response): List<Action> {
        if (mode != Mode.RECONNECT || state != State.WAITING_RESPONSE) return listOf(Action.Ignored)
        val expected = reconnectTag ?: return listOf(Action.Ignored)
        if (response.business != BUSINESS_AUTH || !response.tag.contentEquals(expected)) return listOf(Action.Ignored)
        reconnectTag = null
        if (response.status != STATUS_ACCEPTED || response.port !in 1..MAX_RFCOMM_CHANNEL) {
            state = State.FAILED
            return listOf(Action.Rejected)
        }
        val uuid = response.uuid?.takeIf { it.size == UUID_BYTES } ?: FE36_UUID
        state = State.CONNECTING
        return listOf(Action.ConnectAuthChannel(response.port, uuid))
    }

    private fun reject(request: Request): List<Action> {
        val channel = if (request.channel == 0) CHANNEL_BLUETOOTH else request.channel
        return listOf(response(request.copy(channel = channel, protocol = PROTOCOL_RFCOMM), STATUS_REJECTED, 0, null))
    }

    private fun response(request: Request, status: Int, port: Int, uuid: ByteArray?): Action.SendControl {
        val accepted = status == STATUS_ACCEPTED
        val content = encodeResponse(status, port, request.channel, request.business, request.tag,
            if (accepted) request.protocol else PROTOCOL_RFCOMM, if (accepted) uuid else null)
        return Action.SendControl(encodeTlv(CMD_CREATE_RESPONSE, content))
    }

    private fun serviceUuid(requestUuid: ByteArray?): ByteArray = requestUuid ?: FE36_UUID

    private fun encodeRequest(channel: Int, business: Int, tag: ByteArray, protocol: Int, uuid: ByteArray?): ByteArray {
        val out = ByteArrayBuilder().ea(channel).ea(business).ea(tag.size).bytes(tag).ea(protocol)
        if (uuid != null) out.ea(uuid.size).bytes(uuid)
        return out.result()
    }

    private fun encodeResponse(status: Int, port: Int, channel: Int, business: Int,
                               tag: ByteArray, protocol: Int, uuid: ByteArray?): ByteArray {
        val out = ByteArrayBuilder().ea(status).ea(port).ea(channel).ea(business).ea(tag.size).bytes(tag).ea(protocol)
        if (uuid != null) out.ea(uuid.size).bytes(uuid)
        return out.result()
    }

    private fun encodeTlv(command: Int, value: ByteArray): ByteArray =
        ByteArrayBuilder().ea(command).ea(value.size).bytes(value).result()

    private fun parseSingleTlv(bytes: ByteArray): Pair<Int, ByteArray> {
        if (bytes.size > MAX_CONTROL_PAYLOAD) throw IllegalArgumentException("CONTROL_PAYLOAD_LIMIT")
        val input = Cursor(bytes)
        val command = input.ea()
        val size = input.ea()
        val value = input.bytes(size)
        if (input.remaining != 0) throw IllegalArgumentException("TLV_TRAILING_BYTES")
        return command to value
    }

    private fun parseRequest(bytes: ByteArray): Request {
        val input = Cursor(bytes)
        val channel = input.ea()
        val business = input.ea()
        val tag = input.bytes(input.ea())
        val protocol = input.ea()
        val uuid = if (input.remaining == 0) null else input.bytes(input.ea())
        if (input.remaining != 0) throw IllegalArgumentException("REQUEST_TRAILING_BYTES")
        return Request(channel, business, tag, protocol, uuid)
    }

    private fun parseResponse(bytes: ByteArray): Response {
        val input = Cursor(bytes)
        val status = input.ea()
        val port = input.ea()
        val channel = input.ea()
        val business = input.ea()
        val tag = input.bytes(input.ea())
        val protocol = input.ea()
        val uuid = if (input.remaining == 0) null else input.bytes(input.ea())
        if (input.remaining != 0) throw IllegalArgumentException("RESPONSE_TRAILING_BYTES")
        return Response(status, port, channel, business, tag, protocol, uuid)
    }

    private class Cursor(private val bytes: ByteArray) {
        private var offset = 0
        val remaining: Int get() = bytes.size - offset

        fun ea(): Int {
            var value = 0
            for (index in 0 until EA_MAX_BYTES) {
                if (offset >= bytes.size) throw IllegalArgumentException("EA_TRUNCATED")
                val part = bytes[offset++].toInt() and 0xff
                value = value or ((part and 0x7f) shl (7 * index))
                if (part and 0x80 != 0) return value
            }
            throw IllegalArgumentException("EA_UNTERMINATED")
        }

        fun bytes(size: Int): ByteArray {
            if (size < 0 || size > remaining) throw IllegalArgumentException("FIELD_LENGTH_INVALID")
            return bytes.copyOfRange(offset, offset + size).also { offset += size }
        }
    }

    private class ByteArrayBuilder {
        private val bytes = ArrayList<Byte>()
        fun ea(value: Int): ByteArrayBuilder {
            require(value >= 0) { "EA_NEGATIVE" }
            var rest = value
            do {
                val group = rest and 0x7f
                rest = rest ushr 7
                bytes.add((if (rest == 0) group or 0x80 else group).toByte())
            } while (rest != 0)
            return this
        }
        fun bytes(value: ByteArray): ByteArrayBuilder {
            for (byte in value) bytes.add(byte)
            return this
        }
        fun result(): ByteArray = bytes.toByteArray()
    }

    private companion object {
        const val EA_MAX_BYTES = 4
        const val CMD_CREATE_REQUEST = 3
        const val CMD_CREATE_RESPONSE = 4
        const val BUSINESS_AUTH = 19
        const val CHANNEL_BLUETOOTH = 2
        const val MAX_RFCOMM_CHANNEL = 30
        const val PROTOCOL_RFCOMM = 0
        const val PROTOCOL_TCP = 1
        const val STATUS_ACCEPTED = 0
        const val STATUS_REJECTED = 1
        const val UUID_BYTES = 16
        const val MAX_CONTROL_PAYLOAD = 1024
        val FE36_UUID = byteArrayOf(0x00, 0x00, 0xfe.toByte(), 0x36, 0x00, 0x00, 0x10, 0x00,
            0x80.toByte(), 0x00, 0x00, 0x80.toByte(), 0x5f, 0x9b.toByte(), 0x34, 0xfb.toByte())
        const val MAX_PENDING = 4
    }
}
