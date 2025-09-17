#!/usr/bin/make -f

# Version Makefile

# version from changelog
VERSION := $(shell cd .. && dpkg-parsechangelog -SVersion)
PKGNAME := $(shell cd .. && dpkg-parsechangelog -SSource)

# error handling in case parsechangelog failes
ifeq ($(VERSION),)
    $(error Unable to extract version from changelog)
endif

ifeq ($(PKGNAME),)
    $(error Unable to extract package name from changelog)
endif

# default source and build paths
SOURCE = version.py
BUILD  = build/version.py

# Create build directory
$(shell mkdir -p build)

# default target
all: $(BUILD)

# generate version.py in build directory
$(BUILD): $(SOURCE)
	@sed 's/@PKGNAME@/$(PKGNAME)/g' $(SOURCE) > $(BUILD)
	@sed -i 's/@VERSION@/$(VERSION)/g' $(BUILD)
	@echo "Generated build version for package $(PKGNAME): $(VERSION)"

# Clean target
clean:
	@echo "Cleaned build version"
	@rm -rf build

.PHONY: all clean
