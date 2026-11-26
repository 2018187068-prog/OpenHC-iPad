ARCHS = arm64
TARGET = iphone:clang:latest:15.0
THEOS_PACKAGE_SCHEME = rootless

include $(THEOS)/makefiles/common.mk

TOOL_NAME = openhc-scan-ping-helper
openhc-scan-ping-helper_FILES = main.c
openhc-scan-ping-helper_CFLAGS = -Wall -Wextra -Werror
openhc-scan-ping-helper_INSTALL_PATH = /usr/libexec

include $(THEOS_MAKE_PATH)/tool.mk
