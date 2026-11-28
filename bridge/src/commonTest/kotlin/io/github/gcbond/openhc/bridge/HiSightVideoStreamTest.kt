package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.hisight.Vectors
import io.github.gcbond.openhc.core.hisight.hex
import kotlinx.serialization.json.*
import kotlin.test.*

class HiSightVideoStreamTest {
    private fun wire()=Vectors.section("video").jsonArray.first().jsonObject.getValue("stream").hex()
    @Test fun independentGoldenBytesReachConsumerAndBorrowedPlaintextIsCleared() {
        val key=Vectors.key;var count=0;var borrowed=ByteArray(0);var copied=ByteArray(0)
        val stream=HiSightVideoStream(key,HiSightVideoConsumer {
            count++;borrowed=it.data;copied=it.copyBytes()
            assertEquals(90000L,it.pts90k);assertEquals(listOf(7,8,5),it.nalTypes().toList());true
        })
        key.fill(0);for(byte in wire())assertTrue(stream.feed(byteArrayOf(byte)))
        assertEquals(1,count);assertTrue(copied.any{it!=0.toByte()});assertTrue(borrowed.all{it==0.toByte()})
        assertEquals(1L,stream.deliveredFrames);assertTrue(stream.finish());assertTrue(stream.isClosed)
        assertFalse(stream.hasFailed);assertFalse(stream.feed(wire()));stream.close();stream.close()
    }
    @Test fun sinkFailureIsTerminalAndNeverReplaysBorrowedData() {
        var called=0;val stream=HiSightVideoStream(Vectors.key,HiSightVideoConsumer{called++;false})
        assertFalse(stream.feed(wire()));assertEquals(1,called);assertTrue(stream.hasFailed);assertTrue(stream.isClosed)
        assertEquals(0L,stream.deliveredFrames);assertFalse(stream.feed(wire()));assertEquals(1,called)
    }
    @Test fun partialEofAndBoundViolationsFailClosed() {
        val stream=HiSightVideoStream(Vectors.key,HiSightVideoConsumer{error("unexpected callback")})
        assertTrue(stream.feed(wire().copyOf(10)));assertFalse(stream.finish());assertTrue(stream.hasFailed)
        for(bytes in listOf(ByteArray(0),ByteArray(65537),byteArrayOf(0,0,0,0))) {
            val bad=HiSightVideoStream(Vectors.key,HiSightVideoConsumer{error("unexpected callback")})
            assertFalse(bad.feed(bytes));assertTrue(bad.isClosed);assertTrue(bad.hasFailed)
        }
    }
    @Test fun cancellationDuringConsumerStopsLaterCoalescedFrames() {
        lateinit var stream:HiSightVideoStream;var calls=0
        stream=HiSightVideoStream(Vectors.key,HiSightVideoConsumer{calls++;stream.close();true})
        assertFalse(stream.feed(wire()+wire()));assertEquals(1,calls);assertTrue(stream.isClosed)
    }
}
