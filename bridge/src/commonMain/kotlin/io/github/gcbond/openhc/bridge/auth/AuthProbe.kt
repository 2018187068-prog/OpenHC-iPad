package io.github.gcbond.openhc.bridge.auth

internal object AuthProbe {
    fun run(): String = try {
        AuthVectors.sha256Fips180Vector()
        AuthVectors.hmacSha256Rfc4231()
        AuthVectors.hkdfRfc5869()
        AuthVectors.aesGcmStandardVector()
        AuthVectors.ed25519Rfc8032()
        AuthVectors.x25519Rfc7748()
        SpekeMathProbe.run()
        "AUTH_VECTORS_OK"
    } catch (_: Exception) {
        "AUTH_VECTORS_FAILED"
    }
}
