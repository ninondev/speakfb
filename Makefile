# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
SWIFTC ?= swiftc
MODULE_CACHE ?= /tmp/speakfb-module-cache

.PHONY: all test
all: speakfb

speakfb: speakfb.swift
	mkdir -p "$(MODULE_CACHE)"
	$(SWIFTC) -parse-as-library -O -module-cache-path "$(MODULE_CACHE)" speakfb.swift -o speakfb

test: speakfb
	sh tests/smoke.sh
