ARCHS = arm64
TARGET = iphone:clang:latest:15.0
THEOS_PACKAGE_SCHEME = rootless
# Native dpkg removed lzma output; Theos deb.mk exposes this compression knob.
THEOS_PLATFORM_DEB_COMPRESSION_TYPE = xz

include $(THEOS)/makefiles/common.mk

# Explicit archive writer: Darwin dm.pl otherwise preserves the builder IDs.
override _THEOS_PLATFORM_DPKG_DEB := $(THEOS_PROJECT_DIR)/../../scripts/scan-demo-dpkg-deb.sh

APPLICATION_NAME = OpenHCScanDemo
OpenHCScanDemo_FILES = main.m ScanDemo.m ScanQRCode.m ../scan-supervisor/ScanHelperClient.m
OpenHCScanDemo_FRAMEWORKS = UIKit Foundation CoreImage CoreGraphics QuartzCore OpenHCBridge
OpenHCScanDemo_CFLAGS = -F$(THEOS_PROJECT_DIR)/../../artifacts/iosArm64
OpenHCScanDemo_LDFLAGS = -F$(THEOS_PROJECT_DIR)/../../artifacts/iosArm64
OpenHCScanDemo_OBJCFLAGS = -fobjc-arc

include $(THEOS_MAKE_PATH)/application.mk
