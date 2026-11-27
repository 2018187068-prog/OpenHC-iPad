package io.github.gcbond.openhc.bridge.hicarauth

import io.github.gcbond.openhc.core.common.MalformedMessageException
import io.github.gcbond.openhc.core.nearby.nearbySecureRandomBytes
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/** Configuration supplied by a future trusted platform adapter; never a file loader. */
class AuthServiceIdentity(val packageName: String, val serviceType: String) {
    init { require(packageName.isNotEmpty() && serviceType.isNotEmpty()) }
    override fun toString() = "AuthServiceIdentity(redacted)"
}

/** Entropy injection is for internal tests. The public FE36 coordinator constructor always uses platform CSPRNG. */
interface AuthRandom {
    fun nextBytes(bytes: ByteArray)
    fun nextInt(bound: Int): Int {
        require(bound > 0)
        val bytes = ByteArray(4)
        // Rejection sampling from 31 bits, equivalent uniform range to SecureRandom.nextInt.
        val limit = 0x80000000L - 0x80000000L % bound
        repeat(128) {
            nextBytes(bytes)
            val value = ((bytes[0].toLong() and 127) shl 24) or
                ((bytes[1].toLong() and 255) shl 16) or
                ((bytes[2].toLong() and 255) shl 8) or (bytes[3].toLong() and 255)
            if (value < limit) { bytes.fill(0); return (value % bound).toInt() }
        }
        bytes.fill(0); error("AUTH_ENTROPY_REJECTED")
    }
}
internal object PlatformAuthRandom : AuthRandom {
    override fun nextBytes(bytes: ByteArray) {
        val fresh = nearbySecureRandomBytes(bytes.size)
        fresh.copyInto(bytes); fresh.fill(0)
    }
}
internal fun constantTimeEqual(a: ByteArray, b: ByteArray): Boolean {
    if (a.size != b.size) return false
    var difference = 0
    for (i in a.indices) difference = difference or (a[i].toInt() xor b[i].toInt())
    return difference == 0
}
internal fun ByteArray.toHex(upperCase: Boolean = false): String =
    joinToString("") { (it.toInt() and 255).toString(16).padStart(2, '0') }.let { if (upperCase) it.uppercase() else it }

internal object JsonCodec {
    fun parse(text: String, what: String): JsonElement {
        if (text.length > 10240) throw MalformedMessageException("AUTH_JSON_LIMIT")
        // Also bounds JSON nested inside the outer data string before recursive DOM parsing.
        var depth = 0; var quoted = false; var escaped = false
        for (c in text) {
            if (quoted) {
                when { escaped -> escaped = false; c == '\\' -> escaped = true; c == '"' -> quoted = false }
            } else when (c) {
                '"' -> quoted = true
                '{', '[' -> { depth++; if (depth > 32) throw MalformedMessageException("AUTH_JSON_DEPTH") }
                '}', ']' -> depth--
            }
        }
        return try { Json.parseToJsonElement(text) }
        catch (_: Exception) { throw MalformedMessageException("AUTH_JSON_INVALID") }
    }
    fun parseObject(text: String, what: String): JsonObject =
        parse(text, what) as? JsonObject ?: throw MalformedMessageException("AUTH_JSON_OBJECT_REQUIRED")
}
