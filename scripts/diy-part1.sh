#!/bin/bash
# 运行目录：openwrt 源码根目录，feeds update 之前执行
set -euo pipefail

# OpenClash（官方 feed 没有，直接克隆进 package/）
git clone --depth 1 -b dev https://github.com/vernesong/OpenClash.git package/OpenClash
