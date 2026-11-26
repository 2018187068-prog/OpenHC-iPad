package io.github.gcbond.openhc.core.nearby

import io.github.gcbond.openhc.bridge.auth.HmacSha256
import io.github.gcbond.openhc.bridge.auth.NearbyAesCfb

/** FE35 frame crypto ported from the pinned NearbyFrameCipher algorithm. */
internal class NearbyFrameCipher(rootKey: ByteArray, constA: ByteArray, constB: ByteArray) {
    private var derivedRoot: ByteArray

    init {
        require(rootKey.size >= MIN_KEY_MATERIAL && rootKey.size == constA.size && rootKey.size == constB.size) {
            "NEARBY_KEY_MATERIAL_INVALID"
        }
        val n = rootKey.size
        val h1 = ByteArray(n) { i -> (constA[(i + 3) % n].toInt() xor constB[i].toInt()).toByte() }
        derivedRoot = ByteArray(n) { i -> (h1[(i - 5 + n) % n].toInt() xor rootKey[i].toInt()).toByte() }
        h1.fill(0)
    }

    fun encrypt(plain: ByteArray, seed: ByteArray): ByteArray = crypt(plain, seed, encrypt = true)
    fun decrypt(ciphertext: ByteArray, seed: ByteArray): ByteArray = crypt(ciphertext, seed, encrypt = false)
    fun seal(outerType: Int, plain: ByteArray, seed: ByteArray): NearbyFrame =
        NearbyFrame.encrypted(outerType, encrypt(plain, seed), seed)
    fun open(frame: NearbyFrame): ByteArray = frame.seed?.let { decrypt(frame.payloadView(), it) } ?: frame.payload

    fun close() {
        derivedRoot.fill(0)
        derivedRoot = ByteArray(0)
    }

    private fun crypt(input: ByteArray, seed: ByteArray, encrypt: Boolean): ByteArray {
        check(derivedRoot.isNotEmpty()) { "NEARBY_CIPHER_CLOSED" }
        require(seed.size == NearbyFrame.SEED_LENGTH) { "NEARBY_SEED_INVALID" }
        val material = HmacSha256.mac(derivedRoot, seed)
        val key = material.copyOfRange(0, 16)
        val iv = material.copyOfRange(16, 32)
        return try {
            NearbyAesCfb.crypt(key, iv, input, encrypt)
        } finally {
            material.fill(0)
            key.fill(0)
            iv.fill(0)
        }
    }

    override fun toString(): String = "NearbyFrameCipher(content hidden)"

    private companion object { const val MIN_KEY_MATERIAL = 5 }
}
