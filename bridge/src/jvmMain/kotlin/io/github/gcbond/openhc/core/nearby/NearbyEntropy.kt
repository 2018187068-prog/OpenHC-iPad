package io.github.gcbond.openhc.core.nearby

import java.security.SecureRandom

private val random = SecureRandom()

internal actual fun nearbySecureRandomBytes(size: Int): ByteArray = ByteArray(size).also(random::nextBytes)
