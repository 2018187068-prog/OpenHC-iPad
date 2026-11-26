ARCHS = arm64
TARGET = iphone:clang:latest:15.0
THEOS_PACKAGE_SCHEME = rootless

include $(THEOS)/makefiles/common.mk

APPLICATION_NAME = OpenHCScanDemo
OpenHCScanDemo_FILES = main.m ScanDemo.m ScanQRCode.m
OpenHCScanDemo_FRAMEWORKS = UIKit Foundation CoreImage CoreGraphics QuartzCore OpenHCBridge
OpenHCScanDemo_CFLAGS = -F$(THEOS_PROJECT_DIR)/../../artifacts/iosArm64
OpenHCScanDemo_LDFLAGS = -F$(THEOS_PROJECT_DIR)/../../artifacts/iosArm64
OpenHCScanDemo_OBJCFLAGS = -fobjc-arc

include $(THEOS_MAKE_PATH)/application.mk
