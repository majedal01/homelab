#!/bin/bash
# Ensure the iGPU render node exists; heal it if a guest kernel upgrade dropped i915.
[ -e /dev/dri/renderD128 ] && exit 0
modprobe i915 2>/dev/null
[ -e /dev/dri/renderD128 ] && exit 0
if ! modinfo i915 >/dev/null 2>&1; then
  apt-get update -o DPkg::Lock::Timeout=300 -qq || true
  DEBIAN_FRONTEND=noninteractive apt-get install -y -o DPkg::Lock::Timeout=300 -qq \
    "linux-modules-extra-$(uname -r)" linux-firmware || true
fi
modprobe i915 2>/dev/null || true
[ -e /dev/dri/renderD128 ] && logger -t ensure-i915 "render node restored" || logger -t ensure-i915 "FAILED to restore render node"
