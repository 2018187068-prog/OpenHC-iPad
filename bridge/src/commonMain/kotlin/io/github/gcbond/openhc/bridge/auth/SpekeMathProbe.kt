package io.github.gcbond.openhc.bridge.auth

// Synthetic math/key-derivation slice of KeyAgreement.kt; no wire/state-machine claim.
internal object SpekeMathProbe {
    private fun hex(text: String) = text.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    val prime: ByteArray get() = hex("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AAAC42DAD33170D04507A33A85521ABDF1CBA64ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6BF12FFA06D98A0864D87602733EC86A64521F2B18177B200CBBE117577A615D6C770988C0BAD946E208E24FA074E5AB3143DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF")
    fun modPow(base: ByteArray, exponent: ByteArray) = invoke(10, key = base, a = exponent, c = prime, size = 384)!!
    fun valid(value: ByteArray) = invoke(11, key = value, c = prime, size = 1) != null
    fun run() {
        val salt = ByteArray(16) { it.toByte() }
        val generator = modPow(Hkdf.sha256("314159".encodeToByteArray(), salt, "hichain_speke_base_info".encodeToByteArray(),32), byteArrayOf(2))
        val a = ByteArray(32) { (it+1).toByte() }
        val b = ByteArray(32) { (it+33).toByte() }
        val ap = modPow(generator,a)
        val bp = modPow(generator,b)
        check(valid(ap) && valid(bp)) { "SPEKE_PUBLIC_REJECTED" }
        val shared = modPow(bp,a)
        check(shared.contentEquals(modPow(ap,b))) { "SPEKE_SHARED_MISMATCH" }
        val okm = Hkdf.sha256(shared,salt,"hichain_speke_sessionkey_info".encodeToByteArray(),32)
        val hmacKey = okm.copyOfRange(16,32).copyOf(32)
        val proof = HmacSha256.mac(hmacKey,ByteArray(16) { it.toByte() }+ByteArray(16) { (it+16).toByte() })
        val returned = Hkdf.sha256(okm.copyOfRange(0,16),salt,"hichain_return_key".encodeToByteArray(),16)
        check(Sha256.digest(ap+bp+proof+returned).contentEquals(hex("fdfd53da6d056c20801751e4eedcb851b557d78d156653dc13d4b07bdc5b95e4"))) { "SPEKE_SYNTHETIC_VECTOR_MISMATCH" }
        val eight = modPow(byteArrayOf(2),byteArrayOf(3))
        check(eight.size == 384 && eight.last() == 8.toByte() && eight.dropLast(1).all { it == 0.toByte() })
        check(modPow(byteArrayOf(2),byteArrayOf()).last() == 1.toByte())
        val p = prime
        val pm1 = p.copyOf().also { it[it.lastIndex] = 0xfe.toByte() }
        val pm2 = p.copyOf().also { it[it.lastIndex] = 0xfd.toByte() }
        check(modPow(pm1,byteArrayOf(1)).contentEquals(pm1))
        check(!valid(byteArrayOf()) && !valid(byteArrayOf(0)) && !valid(byteArrayOf(1)))
        check(valid(byteArrayOf(2)) && valid(pm2))
        check(!valid(pm1) && !valid(p) && !valid(ByteArray(385).also { it[384]=2 }))
        shared.fill(0); okm.fill(0); hmacKey.fill(0); returned.fill(0); a.fill(0); b.fill(0)
    }
}
