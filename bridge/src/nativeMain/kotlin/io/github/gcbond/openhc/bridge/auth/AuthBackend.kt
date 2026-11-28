@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
package io.github.gcbond.openhc.bridge.auth

import kotlinx.cinterop.*
import openhc.crypto.oh_crypto
import openhc.crypto.oh_dmsdp_ctr

internal actual object AuthBackend {
    actual fun call(op: Int, key: ByteArray, a: ByteArray, b: ByteArray, c: ByteArray, size: Int): ByteArray? {
        // Non-null one-byte backing for empty input, retaining original logical lengths.
        val k = if(key.isEmpty()) ByteArray(1) else key
        val aa = if(a.isEmpty()) ByteArray(1) else a
        val bb = if(b.isEmpty()) ByteArray(1) else b
        val cc = if(c.isEmpty()) ByteArray(1) else c
        val out = ByteArray(maxOf(size,1))
        val result = k.usePinned { kp -> aa.usePinned { ap -> bb.usePinned { bp -> cc.usePinned { cp -> out.usePinned { optr ->
            if (op == 14) oh_dmsdp_ctr(kp.addressOf(0).reinterpret(),key.size,
                ap.addressOf(0).reinterpret(),a.size,cp.addressOf(0).reinterpret(),c.size,optr.addressOf(0).reinterpret(),size)
            else oh_crypto(op, kp.addressOf(0).reinterpret(), key.size,
                ap.addressOf(0).reinterpret(), a.size, bp.addressOf(0).reinterpret(), b.size,
                cp.addressOf(0).reinterpret(), c.size, optr.addressOf(0).reinterpret(), size)
        } } } } }
        if(result != 1) { out.fill(0); return null }
        return out.copyOf(size)
    }
}
