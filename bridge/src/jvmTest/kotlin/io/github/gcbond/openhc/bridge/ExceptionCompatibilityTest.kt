package io.github.gcbond.openhc.bridge

import io.github.gcbond.openhc.core.common.MalformedMessageException
import kotlin.test.Test
import kotlin.test.assertTrue

class ExceptionCompatibilityTest {
    @Test
    fun jvmRetainsIOExceptionCatchCompatibility() {
        var caught = false
        try {
            throw MalformedMessageException("synthetic")
        } catch (_: java.io.IOException) {
            caught = true
        }
        assertTrue(caught)
    }
}
