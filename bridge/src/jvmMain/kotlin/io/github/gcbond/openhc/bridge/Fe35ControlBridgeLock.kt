package io.github.gcbond.openhc.bridge

internal actual class Fe35ControlBridgeLock actual constructor() {
    private val monitor = Any()

    actual fun <T> withLock(block: () -> T): T = synchronized(monitor, block)
}
