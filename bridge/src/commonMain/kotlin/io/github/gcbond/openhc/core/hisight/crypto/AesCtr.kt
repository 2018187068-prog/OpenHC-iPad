package io.github.gcbond.openhc.core.hisight.crypto

import io.github.gcbond.openhc.bridge.auth.invoke

/** Video-only port of pinned HiSight CTR: BE128 counter, IV16 per ES unit.
 * Uses the existing platform adapter, never a second crypto implementation. */
internal class AesCtr(sessionKey:ByteArray) {
    private val key=sessionKey.copyOf().also {require(it.size==KEY_BYTES)}
    private var closed=false
    fun decryptInto(iv:ByteArray,ivOffset:Int,input:ByteArray,inOffset:Int,length:Int,output:ByteArray,outOffset:Int) {
        check(!closed)
        require(ivOffset>=0 && ivOffset<=iv.size-IV_BYTES && inOffset>=0 && inOffset<=input.size &&
            length>0 && length<=input.size-inOffset && outOffset>=0 && outOffset<=output.size && length<=output.size-outOffset)
        val nonce=iv.copyOfRange(ivOffset,ivOffset+IV_BYTES);val encrypted=input.copyOfRange(inOffset,inOffset+length)
        var plain:ByteArray?=null
        try {
            plain=invoke(14,key=key,a=nonce,c=encrypted,size=length) ?: error("HISIGHT_CTR_FAILED")
            check(plain.size==length);plain.copyInto(output,outOffset)
        } finally {nonce.fill(0);encrypted.fill(0);plain?.fill(0)}
    }
    fun close() {key.fill(0);closed=true}
    companion object {const val KEY_BYTES=16;const val IV_BYTES=16}
}
