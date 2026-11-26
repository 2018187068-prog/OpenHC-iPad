@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
package io.github.gcbond.openhc.core.nearby

import kotlinx.cinterop.addressOf
import kotlinx.cinterop.reinterpret
import kotlinx.cinterop.usePinned
import openhc.crypto.oh_random_bytes

internal actual fun nearbySecureRandomBytes(size: Int): ByteArray {
    require(size >= 0)
    val bytes = ByteArray(size)
    if (size == 0) return bytes
    val ok = bytes.usePinned { oh_random_bytes(it.addressOf(0).reinterpret(), size) }
    check(ok == 1) { "SECURE_RANDOM_FAILED" }
    return bytes
}
