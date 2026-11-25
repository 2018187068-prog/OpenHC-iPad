package io.github.gcbond.openhc.bridge.auth

import kotlin.test.Test

class AuthPortabilityTest {
    @Test fun sha256Standard() = AuthVectors.sha256Fips180Vector()
    @Test fun hmacStandard() = AuthVectors.hmacSha256Rfc4231()
    @Test fun hkdfStandard() = AuthVectors.hkdfRfc5869()
    @Test fun aesGcmStandardAndRejections() = AuthVectors.aesGcmStandardVector()
    @Test fun ed25519StandardAndRejections() = AuthVectors.ed25519Rfc8032()
    @Test fun x25519StandardAndRejections() = AuthVectors.x25519Rfc7748()
    @Test fun speke3072SyntheticMathAndBoundaries() = SpekeMathProbe.run()
    @Test fun extraRejectionsAndBounds() {
        check(X25519Keys.agree(ByteArray(31),ByteArray(32)) == null)
        check(AesGcm.decrypt(ByteArray(16),ByteArray(0),byteArrayOf(),ByteArray(16)) == null)
        for (size in listOf(16,24,32)) {
            val key = ByteArray(size) { (it+1).toByte() }
            val iv = ByteArray(12) { it.toByte() }
            val sealed = AesGcm.encrypt(key,iv,byteArrayOf(),byteArrayOf())
            check(AesGcm.decrypt(key,iv,byteArrayOf(),sealed)?.isEmpty() == true)
            check(AesGcm.decrypt(key,iv,byteArrayOf(),sealed.copyOf().also { it[it.lastIndex]=(it.last().toInt() xor 1).toByte() }) == null)
        }
        for (n in listOf(0,8161)) {
            var rejected = false
            try { Hkdf.sha256(byteArrayOf(),byteArrayOf(),byteArrayOf(),n) } catch (_: IllegalArgumentException) { rejected=true }
            check(rejected)
        }
        check(Hkdf.sha256(byteArrayOf(),byteArrayOf(),byteArrayOf(),8160).size == 8160)
    }
}
