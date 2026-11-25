package io.github.gcbond.openhc.core.common

// Explicit Stage-0 platform boundary: JVM preserves IOException ancestry;
// Native uses Exception. Native callers must catch this type explicitly.
expect class MalformedMessageException(message: String, cause: Throwable? = null) : Exception
