package io.github.gcbond.openhc.bridge.auth

// Stage-0 adapter contract. No backend selection for production is implied.
internal expect object AuthBackend {
    fun call(op: Int, key: ByteArray, a: ByteArray, b: ByteArray, c: ByteArray, size: Int): ByteArray?
}
internal fun invoke(op: Int, key: ByteArray = byteArrayOf(), a: ByteArray = byteArrayOf(),
    b: ByteArray = byteArrayOf(), c: ByteArray = byteArrayOf(), size: Int): ByteArray? =
    AuthBackend.call(op, key, a, b, c, size)
internal object Sha256 { fun digest(vararg parts: ByteArray) = invoke(1, a = parts.fold(byteArrayOf()) { x, y -> x + y }, size = 32)!! }
internal object HmacSha256 { fun mac(key: ByteArray, data: ByteArray) = invoke(2, key, data, size = 32)!! }
internal object Hkdf {
    // Reference HKDF loop; System.arraycopy replaced explicitly by common copyInto.
    fun sha256(ikm: ByteArray, salt: ByteArray, info: ByteArray, length: Int): ByteArray {
        require(length in 1..255 * 32)
        val prk = HmacSha256.mac(salt, ikm)
        val out = ByteArray(length)
        var previous = byteArrayOf()
        var offset = 0
        var counter = 1
        while (offset < length) {
            previous = HmacSha256.mac(prk, previous + info + byteArrayOf(counter.toByte()))
            val n = minOf(previous.size, length - offset)
            previous.copyInto(out, offset, 0, n)
            offset += n
            counter++
        }
        return out
    }
}
internal object AesGcm {
    fun encrypt(key: ByteArray, nonce: ByteArray, aad: ByteArray, plain: ByteArray): ByteArray =
        invoke(3, key, nonce, aad, plain, plain.size + 16) ?: error("AES_GCM_ENCRYPT_FAILED")
    fun decrypt(key: ByteArray, nonce: ByteArray, aad: ByteArray, cipherAndTag: ByteArray): ByteArray? {
        if (key.size !in listOf(16,24,32) || nonce.isEmpty() || cipherAndTag.size < 16) return null
        return invoke(4, key, nonce, aad, cipherAndTag, cipherAndTag.size - 16)
    }
}
internal object Ed25519Keys {
    fun publicKey(seed: ByteArray): ByteArray { require(seed.size == 32); return invoke(5, seed, size = 32)!! }
    fun sign(seed: ByteArray, message: ByteArray): ByteArray { require(seed.size == 32); return invoke(6, seed, message, size = 64)!! }
    fun verify(publicKey: ByteArray, message: ByteArray, signature: ByteArray): Boolean =
        publicKey.size == 32 && signature.size == 64 && invoke(7, publicKey, message, signature, size = 1) != null
}
internal object X25519Keys {
    fun publicKey(privateKey: ByteArray): ByteArray { require(privateKey.size == 32); return invoke(8, privateKey, size = 32)!! }
    fun agree(privateKey: ByteArray, peerPublicKey: ByteArray): ByteArray? =
        if (privateKey.size != 32 || peerPublicKey.size != 32) null else invoke(9, privateKey, peerPublicKey, size = 32)
}
