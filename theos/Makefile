ARCHS = arm64
TARGET = iphone:clang:latest:15.0
THEOS_PACKAGE_SCHEME = rootless

include $(THEOS)/makefiles/common.mk

TOOL_NAME = openhc-bridge-check
openhc-bridge-check_FILES = main.m
openhc-bridge-check_FRAMEWORKS = Foundation OpenHCBridge
openhc-bridge-check_FRAMEWORK_SEARCH_PATHS = $(THEOS_PROJECT_DIR)/../artifacts/iosArm64
openhc-bridge-check_INSTALL_PATH = /usr/bin

include $(THEOS_MAKE_PATH)/tool.mk
