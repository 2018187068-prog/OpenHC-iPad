// Same primitives and static crypto libraries already validated by AuthProbe.
package io.github.gcbond.openhc.bridge.hicarauth.crypto
import io.github.gcbond.openhc.bridge.auth.invoke
internal object Sha256 { fun digest(vararg parts: ByteArray) = io.github.gcbond.openhc.bridge.auth.Sha256.digest(*parts) }
internal object HmacSha256 { const val LENGTH=32; fun mac(key: ByteArray, data: ByteArray) = io.github.gcbond.openhc.bridge.auth.HmacSha256.mac(key,data) }
internal object Hkdf { fun sha256(ikm:ByteArray,salt:ByteArray,info:ByteArray,length:Int) = io.github.gcbond.openhc.bridge.auth.Hkdf.sha256(ikm,salt,info,length) }
internal object AesGcm {
 const val TAG_LENGTH=16
 fun encrypt(key:ByteArray,nonce:ByteArray,aad:ByteArray,plain:ByteArray) = io.github.gcbond.openhc.bridge.auth.AesGcm.encrypt(key,nonce,aad,plain)
 fun decrypt(key:ByteArray,nonce:ByteArray,aad:ByteArray,cipherAndTag:ByteArray) = io.github.gcbond.openhc.bridge.auth.AesGcm.decrypt(key,nonce,aad,cipherAndTag)
}
internal object Ed25519Keys {
 const val KEY_LENGTH=32; const val SIGNATURE_LENGTH=64
 fun publicKey(seed:ByteArray) = io.github.gcbond.openhc.bridge.auth.Ed25519Keys.publicKey(seed)
 fun sign(seed:ByteArray,message:ByteArray) = io.github.gcbond.openhc.bridge.auth.Ed25519Keys.sign(seed,message)
 fun verify(publicKey:ByteArray,message:ByteArray,signature:ByteArray) = io.github.gcbond.openhc.bridge.auth.Ed25519Keys.verify(publicKey,message,signature)
}
internal object X25519Keys {
 const val KEY_LENGTH=32
 fun publicKey(privateKey:ByteArray) = io.github.gcbond.openhc.bridge.auth.X25519Keys.publicKey(privateKey)
 fun agree(privateKey:ByteArray,peerPublicKey:ByteArray) = io.github.gcbond.openhc.bridge.auth.X25519Keys.agree(privateKey,peerPublicKey)
}
internal object Modp {
 const val LENGTH_3072=384; const val LENGTH_2048=256
 private fun prime(length:Int):ByteArray = when(length) {
  LENGTH_3072 -> io.github.gcbond.openhc.bridge.auth.SpekeMathProbe.prime
  LENGTH_2048 -> "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF".chunked(2).map { it.toInt(16).toByte() }.toByteArray()
  else -> error("AUTH_MODP_LENGTH")
 }
 fun modPow(base:ByteArray,exponent:ByteArray,length:Int):ByteArray =
  invoke(10,key=base,a=exponent,c=prime(length),size=length) ?: error("AUTH_MODP_FAILED")
 fun isValidPublicValue(value:ByteArray,length:Int):Boolean =
  value.size<=length && invoke(11,key=value,c=prime(length),size=1)!=null
}
