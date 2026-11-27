ARCHS = arm64
TARGET = iphone:clang:latest:15.0
THEOS_PACKAGE_SCHEME = rootless
THEOS_PLATFORM_DEB_COMPRESSION_TYPE = xz

include $(THEOS)/makefiles/common.mk
override _THEOS_PLATFORM_DPKG_DEB := $(THEOS_PROJECT_DIR)/../../scripts/scan-demo-dpkg-deb.sh

# Inert tools only: no LaunchDaemon, postinst, client grant or effect adapter.
# No PROCESS_TEST / OWNER_TEST macro is permitted in this deployment package.
TOOL_NAME = openhc-scan-broker openhc-scan-guard
openhc-scan-broker_FILES = ScanBrokerProcess.c ScanLeaseProtocol.c
openhc-scan-guard_FILES = ScanGuardProcess.c ScanLeaseProtocol.c ScanLeaseChannel.c
openhc-scan-broker_CFLAGS = -std=c11 -Wall -Wextra -Werror
openhc-scan-guard_CFLAGS = -std=c11 -Wall -Wextra -Werror
openhc-scan-broker_INSTALL_PATH = /usr/libexec/openhc-owner-inert
openhc-scan-guard_INSTALL_PATH = /usr/libexec/openhc-owner-inert

include $(THEOS_MAKE_PATH)/tool.mk
