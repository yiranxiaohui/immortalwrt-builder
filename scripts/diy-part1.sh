#!/bin/bash
# 运行目录：openwrt 源码根目录，feeds update 之前执行
set -euo pipefail

# OpenClash（官方 feed 没有，直接克隆进 package/）
git clone --depth 1 -b dev https://github.com/vernesong/OpenClash.git package/OpenClash

# mosdns（feed 只有核心无 LuCI，用 sbwml 维护版 + 配套地理数据包）
git clone --depth 1 -b v5 https://github.com/sbwml/luci-app-mosdns.git package/mosdns
git clone --depth 1 https://github.com/sbwml/v2ray-geodata.git package/v2ray-geodata

# EasyTier（feed 没有，仓库内含 easytier 核心包 + luci-app-easytier）
git clone --depth 1 https://github.com/yiranxiaohui/luci-app-easytier.git package/easytier
