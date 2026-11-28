package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.hisight.AccessUnit
import io.github.gcbond.openhc.core.hisight.AccessUnitSink
import io.github.gcbond.openhc.core.hisight.video.VideoDepacketizer

/** Synchronous consumer; false is a terminal sink failure. Buffers are borrowed
 * only for this callback. Dropped frames are counted by the actual sink. */
fun interface HiSightVideoConsumer {fun accept(unit:AccessUnit):Boolean}

/** Pure HiSight video protocol adapter, not a connection/admission authority.
 * The original receiver owner must supply its private key and serialize every
 * feed/cancel under its existing lease. No network, timer or service declaration.
 * Control/SETUP/PLAY and owner socket attachment remain separate dependencies. */
class HiSightVideoStream(sessionKey:ByteArray,consumer:HiSightVideoConsumer) {
    private val lock=Fe35ControlBridgeLock()
    private val video=VideoDepacketizer(sessionKey,AccessUnitSink{check(!closed && consumer.accept(it) && !closed)})
    private var closed=false
    private var failed=false
    val isClosed:Boolean get()=lock.withLock{closed}
    val hasFailed:Boolean get()=lock.withLock{failed}
    val deliveredFrames:Long get()=lock.withLock{video.framesDelivered}
    fun feed(data:ByteArray):Boolean=lock.withLock {
        if(closed)return@withLock false
        try {
            require(data.isNotEmpty() && data.size<=65536)
            video.feed(data,0,data.size);true
        } catch(_:Exception) {failed=true;closed=true;video.close();false}
    }
    fun finish():Boolean=lock.withLock {
        if(closed)return@withLock false
        try {video.finish();true} catch(_:Exception) {failed=true;false}
        finally {closed=true;video.close()}
    }
    fun close()=lock.withLock {closed=true;video.close()}
    override fun toString()="HiSightVideoStream(redacted)"
}
