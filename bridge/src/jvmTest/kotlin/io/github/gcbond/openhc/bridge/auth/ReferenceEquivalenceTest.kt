package io.github.gcbond.openhc.bridge.auth

import io.github.gcbond.openhc.core.auth.crypto.Hkdf as ReferenceHkdf
import io.github.gcbond.openhc.core.auth.crypto.Modp as ReferenceModp
import kotlin.test.Test

class ReferenceEquivalenceTest {
    @Test fun copiedReferenceHkdfAndModpMatchAdapters() {
        for (length in listOf(1,16,32,42,65,8160)) {
            val input = ByteArray(22) { 11 }
            val salt = ByteArray(16) { it.toByte() }
            val info = "synthetic-info".encodeToByteArray()
            check(Hkdf.sha256(input,salt,info,length).contentEquals(ReferenceHkdf.sha256(input,salt,info,length)))
        }
        for (base in listOf(byteArrayOf(),byteArrayOf(2),SpekeMathProbe.prime)) {
            for (exponent in listOf(byteArrayOf(),byteArrayOf(1),byteArrayOf(3))) {
                check(SpekeMathProbe.modPow(base,exponent).contentEquals(ReferenceModp.modPow(base,exponent,384)))
                check(SpekeMathProbe.valid(base) == ReferenceModp.isValidPublicValue(base,384))
            }
        }
    }
}
