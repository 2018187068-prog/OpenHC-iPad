package io.github.gcbond.openhc.bridge.auth

import io.github.gcbond.openhc.core.auth.crypto.Sha256 as RefSha256
import io.github.gcbond.openhc.core.auth.crypto.HmacSha256 as RefHmacSha256
import io.github.gcbond.openhc.core.auth.crypto.AesGcm as RefAesGcm
import io.github.gcbond.openhc.core.auth.crypto.Ed25519Keys as RefEd25519Keys
import io.github.gcbond.openhc.core.auth.crypto.X25519Keys as RefX25519Keys
import java.math.BigInteger

internal actual object AuthBackend {
    actual fun call(op: Int, key: ByteArray, a: ByteArray, b: ByteArray, c: ByteArray, size: Int): ByteArray? = when(op) {
        1 -> RefSha256.digest(a)
        2 -> RefHmacSha256.mac(key, a)
        3 -> RefAesGcm.encrypt(key, a, b, c)
        4 -> RefAesGcm.decrypt(key, a, b, c)
        5 -> RefEd25519Keys.publicKey(key)
        6 -> RefEd25519Keys.sign(key, a)
        7 -> if (RefEd25519Keys.verify(key, a, b)) byteArrayOf(1) else null
        8 -> RefX25519Keys.publicKey(key)
        9 -> RefX25519Keys.agree(key, a)
        10 -> BigInteger(1,key).modPow(BigInteger(1,a),BigInteger(1,c)).toByteArray().let {
            val unsigned = if (it.size > size && it[0] == 0.toByte()) it.copyOfRange(1,it.size) else it
            ByteArray(size).also { out -> unsigned.copyInto(out,size-unsigned.size) }
        }
        11 -> if (key.size <= c.size && BigInteger(1,key) > BigInteger.ONE && BigInteger(1,key) < BigInteger(1,c)-BigInteger.ONE) byteArrayOf(1) else null
        else -> error("UNSUPPORTED_OPERATION")
    }
}
