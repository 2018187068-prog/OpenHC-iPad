# Authentication portability probe (Stage 0)

## Scope and provenance

Reference OpenHC: `8132399bea6aa86d68da6d3e1d9e3e001c0a7643`. `AuthCrypto.kt` is copied without algorithm edits into jvmMain and pinned in `scripts/source-slices.sha256`. Bouncy Castle 1.79 matches the reference catalog and is used only by the JVM comparator. First six standard-vector methods in `CryptoTest.kt` are adapted into commonMain `AuthVectors`: `toByteArray()` becomes `encodeToByteArray()` for ASCII fixtures; assertions emit only a generic failure, never bytes. No identity asset is read.

The common adapter mirrors the reference HKDF loop with `copyInto` replacing `System.arraycopy`. JVM actual delegates primitives to the copied reference; a separate JVM equivalence test also compares HKDF, unsigned big-endian MODP operations and public-value validation against reference functions. This is a bounded compatibility probe, not a migration of `PakeServer`, STS, identity exchange or session code.

## Candidate Native backend

OpenSSL tag `openssl-3.5.9`, peeled commit `45e844fa2a14ec92d146bd8f5778ac130b6625fb`, is pinned and verified after clone. This version is a reproducibility choice for this candidate, not a claim of optimality. Build logs preserve the upstream iOS configuration and toolchain/version; device and arm64-simulator libraries are built separately with deployment minimum 15.0. Native cinterop embeds the C shim and libcrypto as static libraries. The final executable must have no libcrypto/libssl dynamic dependency.

`native/crypto/openhc_crypto.c` maps SHA-256/HMAC/AES-GCM/Ed25519/X25519 through OpenSSL APIs, and MODP through unsigned BIGNUM conversion with fixed-width output and `BN_mod_exp_mont_consttime`. Device acceptance and performance on A8 still need a physical run. No timing/side-channel audit, production backend selection or complete equivalence for every invalid curve encoding is claimed. The shim suppresses OpenSSL diagnostics and wipes failed output buffers. All key material in the probe consists of public-standard vectors or synthetic fixtures.

## Evidence required

- Standard SHA-256, HMAC, HKDF, AES-GCM with AAD, Ed25519 and X25519 vectors on both JVM and iosSimulatorArm64.
- AES-GCM tampered payload/tag, wrong AAD, short cipher, bad key/nonce; X25519 small-order/zero and length rejection; Ed25519 changed message/wrong key/length rejection.
- HKDF boundaries, including 8160 bytes; JVM reference equivalence.
- Synthetic SPEKE3072 math slice: generator from HKDF(PIN,salt,base-info)^2, two fixed private exponents, both public/shared values, directional proof and return-key derivation. Verify against an independent Python big-int/HMAC/HKDF oracle fingerprint without printing any derived value. Verify zero/one/p-1/p/oversize rejection and fixed-width unsigned output. This is not a real HiCar transcript or full state-machine test.
- Static arm64 iOS-15 framework and signed rootless 0.3.0 DEB, followed by a physical `--auth` run returning `AUTH_VECTORS_OK`.

## Commands in the 0.3.0 package

```sh
/var/jb/usr/bin/openhc-bridge-check --version
/var/jb/usr/bin/openhc-bridge-check --auth
/var/jb/usr/bin/openhc-bridge-check --platform
```

Expected first two lines respectively: `OPENHC_STAGE0_VERSION=0.3.0`, `AUTH_VECTORS_OK`. The third command inventories hardware/OS, IPv4 interfaces, class/symbol availability and known BTstack files/socket. It does not read passwords, instantiate MISManager, change sharing state or connect a Bluetooth socket. `PLATFORM_INVENTORY_DONE` means the inventory completed, not that an AP or FE35/FE36 is working. Actual SSID/BSSID/frequency remain explicitly UNVERIFIED.

## Current status

Implementation prepared; CI and new physical results pending. First CI run `45648844771` failed at OpenSSL Configure because an extra `-arch arm64` argument was treated as a second target. Removed it: the fixed upstream ios64/iossimulator-arm64 target already declares the architecture. No protocol behavior changed for that fix.
