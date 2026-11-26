package io.github.gcbond.openhc.core.nearby

import io.github.gcbond.openhc.core.common.ByteWriter

/** FE35 actions derived from a decoded message-layer payload. */
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
        data object Discarded : Action()
        data object Rejected : Action()
        data object CloseAuthListener : Action()
        data object AbortControl : Action()
    }

    private enum class State { READY, LISTENING, LISTENING_OPEN, WAITING_RESPONSE, CONNECTING, COMPLETE, FAILED }
    private sealed class Message {
        class Request(val value: SocketMessages.Request) : Message()
        class Response(val value: SocketMessages.Response) : Message()
        data object Other : Message()
    }

    private var state = State.READY
    private val pending = ArrayList<SocketMessages.Request>(MAX_PENDING)
    private var localChannel = 0
    private var reconnectTag: ByteArray? = null

    fun requestAuthChannel(tag: ByteArray): Action.SendControl {
        check(mode == Mode.RECONNECT && state == State.READY) { "AUTH_REQUEST_OUT_OF_ORDER" }
        require(tag.isNotEmpty() && tag.size <= MAX_TAG_BYTES) { "AUTH_TAG_SIZE_INVALID" }
        reconnectTag = tag.copyOf()
        state = State.WAITING_RESPONSE
        return Action.SendControl(encodeTlv(SocketMessages.CMD_CREATE_REQUEST,
            SocketMessages.encodeRequest(SocketMessages.Request(CHANNEL_BLUETOOTH, BUSINESS_AUTH, tag, 0, null))))
    }

    /** Parses the full message layer before applying any state changes, as NearbySession does. */
    fun onMessageLayerPayload(payload: ByteArray): List<Action> {
        check(state != State.FAILED) { "CONTROL_NEGOTIATION_CLOSED" }
        if (payload.size > MAX_CONTROL_PAYLOAD) return listOf(Action.Discarded)
        val messages = try {
            Tlv.parseAll(payload).map { item ->
                when (item.tag) {
                    SocketMessages.CMD_CREATE_REQUEST -> Message.Request(SocketMessages.parseRequest(item.valueView()))
                    SocketMessages.CMD_CREATE_RESPONSE -> Message.Response(SocketMessages.parseResponse(item.valueView()))
                    else -> Message.Other
                }
            }
        } catch (_: Exception) {
            return listOf(Action.Discarded)
        }
        val out = ArrayList<Action>()
        for (message in messages) {
            out += when (message) {
                is Message.Request -> onRequest(message.value)
                is Message.Response -> onResponse(message.value)
                Message.Other -> listOf(Action.Ignored)
            }
        }
        return out
    }

    fun onAuthListenerReady(channel: Int): List<Action> {
        check(mode == Mode.PASSIVE && state == State.LISTENING) { "LISTENER_CALLBACK_OUT_OF_ORDER" }
        if (channel !in 1..MAX_RFCOMM_CHANNEL) {
            state = State.FAILED
            val rejected = pending.map { response(it, SocketMessages.STATUS_REJECTED, 0, null) }
            pending.clear()
            return rejected + listOf(Action.CloseAuthListener, Action.AbortControl)
        }
        localChannel = channel
        state = State.LISTENING_OPEN
        val result = pending.map { response(it, SocketMessages.STATUS_ACCEPTED, channel, serviceUuid(it.uuid)) }
        pending.clear()
        return result
    }

    fun onAuthConnected() {
        check(mode == Mode.PASSIVE && state == State.LISTENING_OPEN) { "AUTH_CONNECT_OUT_OF_ORDER" }
        state = State.COMPLETE
    }

    fun close() {
        pending.clear()
        reconnectTag = null
        state = State.FAILED
    }

    private fun onRequest(request: SocketMessages.Request): List<Action> {
        if (mode != Mode.PASSIVE) return listOf(Action.Ignored)
        if (state != State.READY && state != State.LISTENING && state != State.LISTENING_OPEN) {
            return reject(request)
        }
        if (request.businessId != BUSINESS_AUTH || request.protocol and PROTOCOL_TCP != 0 ||
            (request.uuid != null && request.uuid.size != UUID_BYTES)) return reject(request)

        val normalized = if (request.channel == 0) CHANNEL_BLUETOOTH else request.channel
        val accepted = SocketMessages.Request(normalized, request.businessId, request.tag, request.protocol, request.uuid)
        return when (state) {
            State.READY -> {
                state = State.LISTENING
                pending += accepted
                listOf(Action.OpenAuthListener(serviceUuid(request.uuid)))
            }
            State.LISTENING -> if (pending.size >= MAX_PENDING) reject(request) else {
                pending += accepted
                listOf(Action.Ignored)
            }
            State.LISTENING_OPEN -> listOf(response(accepted, SocketMessages.STATUS_ACCEPTED, localChannel,
                serviceUuid(request.uuid)))
            else -> reject(request)
        }
    }

    private fun onResponse(response: SocketMessages.Response): List<Action> {
        if (mode != Mode.RECONNECT || state != State.WAITING_RESPONSE) return listOf(Action.Ignored)
        val expected = reconnectTag ?: return listOf(Action.Ignored)
        if (response.businessId != BUSINESS_AUTH || !response.tag.contentEquals(expected)) return listOf(Action.Ignored)
        reconnectTag = null
        if (response.status != SocketMessages.STATUS_ACCEPTED || response.port !in 1..MAX_RFCOMM_CHANNEL) {
            state = State.FAILED
            return listOf(Action.Rejected)
        }
        val uuid = response.uuid?.takeIf { it.size == UUID_BYTES } ?: FE36_UUID
        state = State.CONNECTING
        return listOf(Action.ConnectAuthChannel(response.port, uuid))
    }

    private fun reject(request: SocketMessages.Request): List<Action> {
        val channel = if (request.channel == 0) CHANNEL_BLUETOOTH else request.channel
        val normalized = SocketMessages.Request(channel, request.businessId, request.tag, PROTOCOL_RFCOMM, null)
        return listOf(response(normalized, SocketMessages.STATUS_REJECTED, 0, null))
    }

    private fun response(request: SocketMessages.Request, status: Int, port: Int, uuid: ByteArray?): Action.SendControl =
        Action.SendControl(SocketMessages.responsePayload(status, port, request.channel, request.businessId,
            request.tag, if (status == SocketMessages.STATUS_ACCEPTED) request.protocol else PROTOCOL_RFCOMM, uuid))

    private fun serviceUuid(requestUuid: ByteArray?): ByteArray = requestUuid ?: FE36_UUID

    private fun encodeTlv(command: Int, value: ByteArray): ByteArray = ByteWriter(value.size + 8)
        .tlv(command, value).toByteArray()

    private companion object {
        const val BUSINESS_AUTH = 19
        const val CHANNEL_BLUETOOTH = 2
        const val MAX_RFCOMM_CHANNEL = 30
        const val PROTOCOL_RFCOMM = 0
        const val PROTOCOL_TCP = 1
        const val UUID_BYTES = 16
        const val MAX_CONTROL_PAYLOAD = 1024
        const val MAX_TAG_BYTES = 256
        const val MAX_PENDING = 4
        val FE36_UUID = byteArrayOf(0x00, 0x00, 0xfe.toByte(), 0x36, 0x00, 0x00, 0x10, 0x00,
            0x80.toByte(), 0x00, 0x00, 0x80.toByte(), 0x5f, 0x9b.toByte(), 0x34, 0xfb.toByte())
    }
}
