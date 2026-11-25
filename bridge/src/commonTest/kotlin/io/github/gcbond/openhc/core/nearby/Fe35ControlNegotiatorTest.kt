package io.github.gcbond.openhc.core.nearby

import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertTrue

class Fe35ControlNegotiatorTest {
    private val authRequest = hex("838d86938968696361724175746880")
    private val fe36 = hex("0000fe3600001000800000805f9b34fb")

    @Test
    fun passiveOpenThenReplyMatchesPinnedOpenHcVector() {
        val machine = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
        val open = assertIs<Fe35ControlNegotiator.Action.OpenAuthListener>(
            machine.onMessageLayerPayload(authRequest).single())
        assertContentEquals(fe36, open.uuid)
        val reply = assertIs<Fe35ControlNegotiator.Action.SendControl>(machine.onAuthListenerReady(4).single())
        assertContentEquals(
            hex("84a0808482938968696361724175746880900000fe3600001000800000805f9b34fb"), reply.payload)
        machine.onAuthConnected()
        assertIs<Fe35ControlNegotiator.Action.SendControl>(machine.onMessageLayerPayload(authRequest).single())
    }

    @Test
    fun duplicatePassiveRequestsQueueAndChannelZeroMapsToBluetoothChannel() {
        val machine = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
        machine.onMessageLayerPayload(hex("838d80938968696361724175746881")).single()
        assertIs<Fe35ControlNegotiator.Action.Ignored>(machine.onMessageLayerPayload(authRequest).single())
        val replies = machine.onAuthListenerReady(30)
        assertEquals(2, replies.size)
        val first = assertIs<Fe35ControlNegotiator.Action.SendControl>(replies[0]).payload
        val second = assertIs<Fe35ControlNegotiator.Action.SendControl>(replies[1]).payload
        assertTrue(first.contentEquals(hex("84a1801e8082938968696361724175746880900000fe3600001000800000805f9b34fb")))
        assertTrue(second.contentEquals(hex("84a1801e8682938968696361724175746880900000fe3600001000800000805f9b34fb")))
    }

    @Test
    fun invalidRequestsAreRejectedAndBadLengthsFailClosed() {
        val machine = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
        val wrongBusiness = hex("838d86928968696361724175746881")
        val rejected = assertIs<Fe35ControlNegotiator.Action.SendControl>(
            machine.onMessageLayerPayload(wrongBusiness).single()).payload
        assertTrue(rejected.contentEquals(hex("848f818086928968696361724175746880")))

        val invalidUuid = hex("83918693896869636172417574688083010203")
        assertIs<Fe35ControlNegotiator.Action.SendControl>(machine.onMessageLayerPayload(invalidUuid).single())
        val malformed = machine.onMessageLayerPayload(hex("838d8693896869"))
        assertIs<Fe35ControlNegotiator.Action.AbortControl>(malformed.single())
        assertFailsWith<IllegalStateException> { machine.onMessageLayerPayload(authRequest) }

        val opening = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
        opening.onMessageLayerPayload(authRequest)
        val cleanup = opening.onMessageLayerPayload(hex("838d8693896869"))
        assertIs<Fe35ControlNegotiator.Action.CloseAuthListener>(cleanup[0])
        assertIs<Fe35ControlNegotiator.Action.AbortControl>(cleanup[1])
    }

    @Test
    fun suppliedSixteenByteUuidIsUsedAndOutOfRangeListenerChannelIsRejected() {
        val supplied = hex("101112131415161718191a1b1c1d1e1f")
        val request = hex("839e8693896869636172417574688090") + supplied
        val machine = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
        val listener = assertIs<Fe35ControlNegotiator.Action.OpenAuthListener>(
            machine.onMessageLayerPayload(request).single())
        assertContentEquals(supplied, listener.uuid)
        val reply = assertIs<Fe35ControlNegotiator.Action.SendControl>(machine.onAuthListenerReady(1).single())
        assertTrue(reply.payload.contentEquals(
            hex("84a080818693896869636172417574688090101112131415161718191a1b1c1d1e1f")))

        val invalid = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
        invalid.onMessageLayerPayload(authRequest)
        val failed = invalid.onAuthListenerReady(31)
        val rejected = assertIs<Fe35ControlNegotiator.Action.SendControl>(failed[0])
        assertTrue(rejected.payload.contentEquals(hex("848f818086938968696361724175746880")))
        assertIs<Fe35ControlNegotiator.Action.CloseAuthListener>(failed[1])
        assertIs<Fe35ControlNegotiator.Action.AbortControl>(failed[2])
    }

    @Test
    fun rfcommIsSelectedByAbsenceOfTcpCapabilityBit() {
        val request = hex("838d86938968696361724175746882")
        val machine = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.PASSIVE)
        assertIs<Fe35ControlNegotiator.Action.OpenAuthListener>(machine.onMessageLayerPayload(request).single())
    }

    @Test
    fun reconnectRequestAndResponseFollowUpstreamDirectionAndDefaults() {
        val machine = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.RECONNECT)
        val tag = "Phone".encodeToByteArray()
        val request = machine.requestAuthChannel(tag)
        assertContentEquals(hex("838982938550686f6e6580"), request.payload)
        assertIs<Fe35ControlNegotiator.Action.Ignored>(machine.onMessageLayerPayload(authRequest).single())
        val unmatched = hex("848b80888293854f7468657280")
        assertIs<Fe35ControlNegotiator.Action.Ignored>(machine.onMessageLayerPayload(unmatched).single())
        val response = hex("848b808882938550686f6e6580")
        val connect = assertIs<Fe35ControlNegotiator.Action.ConnectAuthChannel>(
            machine.onMessageLayerPayload(response).single())
        assertEquals(8, connect.channel)
        assertContentEquals(fe36, connect.uuid)
        assertFailsWith<IllegalStateException> { machine.requestAuthChannel(tag) }
        assertIs<Fe35ControlNegotiator.Action.Ignored>(machine.onMessageLayerPayload(response).single())
    }

    @Test
    fun reconnectRejectsStatusAndOutOfRangeChannelAndUsesOnlySixteenByteUuid() {
        fun fresh() = Fe35ControlNegotiator(Fe35ControlNegotiator.Mode.RECONNECT).also {
            it.requestAuthChannel("Phone".encodeToByteArray())
        }
        val refused = fresh().onMessageLayerPayload(hex("848b818082938550686f6e6580")).single()
        assertIs<Fe35ControlNegotiator.Action.Rejected>(refused)
        assertIs<Fe35ControlNegotiator.Action.Rejected>(
            fresh().onMessageLayerPayload(hex("848b809f82938550686f6e6580")).single())
        val badUuid = hex("848f808882938550686f6e658083010203")
        val connect = assertIs<Fe35ControlNegotiator.Action.ConnectAuthChannel>(
            fresh().onMessageLayerPayload(badUuid).single())
        assertContentEquals(fe36, connect.uuid)
    }

    private fun hex(text: String): ByteArray = ByteArray(text.length / 2) { index ->
        text.substring(index * 2, index * 2 + 2).toInt(16).toByte()
    }
}
