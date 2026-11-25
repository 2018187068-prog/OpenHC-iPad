package io.github.gcbond.openhc.core.nearby

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class WifiChannelsTest {
    @Test
    fun frequencyAndChannelBoundaries() {
        assertEquals(2412, WifiChannels.frequencyOf(1))
        assertEquals(2472, WifiChannels.frequencyOf(13))
        assertEquals(2484, WifiChannels.frequencyOf(14))
        assertEquals(5160, WifiChannels.frequencyOf(32))
        assertEquals(5885, WifiChannels.frequencyOf(177))
        assertFailsWith<IllegalArgumentException> { WifiChannels.frequencyOf(0) }
        assertFailsWith<IllegalArgumentException> { WifiChannels.frequencyOf(31) }
        assertFailsWith<IllegalArgumentException> { WifiChannels.frequencyOf(178) }
    }

    @Test
    fun frequencyLookupAndBands() {
        assertEquals(1, WifiChannels.channelOf(2412))
        assertEquals(14, WifiChannels.channelOf(2484))
        assertEquals(149, WifiChannels.channelOf(5745))
        assertNull(WifiChannels.channelOf(2413))
        assertNull(WifiChannels.channelOf(5150))
        assertNull(WifiChannels.channelOf(5890))
        assertTrue(WifiChannels.is2g(2484))
        assertFalse(WifiChannels.is2g(2485))
        assertTrue(WifiChannels.is5g(5745))
        assertFalse(WifiChannels.is5g(5747))
    }

    @Test
    fun bitmapUsesDefinedChannelOrderAndIgnoresUnknownBits() {
        assertEquals(0b100000001L, WifiChannels.bitmapOf(listOf(36, 165)))
        assertEquals(setOf(36, 165), WifiChannels.channelsOf(0b100000001L or (1L shl 20)))
        assertEquals(0L, WifiChannels.bitmapOf(emptyList()))
        assertFailsWith<IllegalArgumentException> { WifiChannels.bitmapOf(listOf(32)) }
    }
}
