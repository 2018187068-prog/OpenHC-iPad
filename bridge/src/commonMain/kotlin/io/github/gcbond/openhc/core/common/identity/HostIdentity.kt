package io.github.gcbond.openhc.core.common.identity

/** In-memory host fields from OpenHC 8132399bea6aa86d68da6d3e1d9e3e001c0a7643 IdentityAssets.kt.
 * No JSON/assets dependency. Unlike the upstream data class, diagnostics redact all fields. */
class HostIdentity(
    val modelId: String,
    val subModelId: String,
    val brand: String,
    val deviceName: String,
) {
    init {
        require(Regex("[0-9A-F]{6}").matches(modelId)) { "MODEL_ID_INVALID" }
        require(Regex("[0-9A-F]{2}").matches(subModelId)) { "SUBMODEL_ID_INVALID" }
        require(brand.isNotBlank()) { "BRAND_INVALID" }
        require(deviceName.isNotBlank()) { "DEVICE_NAME_INVALID" }
    }
    val fullModel: String get() = modelId + subModelId
    override fun toString(): String = "HostIdentity(redacted)"
}
