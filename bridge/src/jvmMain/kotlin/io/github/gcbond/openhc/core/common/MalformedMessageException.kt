package io.github.gcbond.openhc.core.common

actual class MalformedMessageException actual constructor(message: String, cause: Throwable?) :
    java.io.IOException(message, cause)
