#!/bin/bash
# 运行目录：openwrt 源码根目录，.config 拷入之后、make defconfig 之前执行
# 职责：准备 files/ 覆盖层——首启扩容脚本 + OpenClash 离线内核与数据库
set -euxo pipefail

# 删除 feed 自带的 mosdns，避免与 sbwml 版（package/mosdns）版本冲突
rm -rf feeds/packages/net/mosdns feeds/packages/net/msd_lite

# 默认 LAN IP 改为 192.168.0.1（写入固件默认值，恢复出厂后依然生效）
sed -i 's/192\.168\.1\.1/192.168.0.1/g' package/base-files/files/bin/config_generate

mkdir -p files/etc/uci-defaults files/etc/openclash/core

# 首启自动扩容脚本（来自仓库 files/）
cp "$GITHUB_WORKSPACE"/files/etc/uci-defaults/* files/etc/uci-defaults/
chmod +x files/etc/uci-defaults/*

# 扩容标记文件在 sysupgrade 后保留，避免重复扩容
cat >> files/etc/sysupgrade.conf <<'EOF'
/etc/rootpt-resize
/etc/rootfs-resize
EOF

# mihomo 内核（OpenClash Meta 内核，预置避免首次启动联网下载）
# 带 token 认证，匿名调 GitHub API 在 Actions runner 上经常被限流
AUTH=()
[ -n "${GITHUB_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer $GITHUB_TOKEN")
CORE_VER=$(curl -sL "${AUTH[@]}" https://api.github.com/repos/MetaCubeX/mihomo/releases/latest | grep -oP '"tag_name": "\K[^"]+' || true)
if [ -z "$CORE_VER" ]; then
  echo "ERROR: 获取 mihomo 最新版本失败（GitHub API 限流或网络问题）" >&2
  exit 1
fi
echo "mihomo version: $CORE_VER"
curl -sfL "https://github.com/MetaCubeX/mihomo/releases/download/${CORE_VER}/mihomo-linux-amd64-${CORE_VER}.gz" \
  | gunzip > files/etc/openclash/core/clash_meta
chmod +x files/etc/openclash/core/clash_meta

# GeoIP / GeoSite / Country.mmdb
curl -sfL -o files/etc/openclash/Country.mmdb \
  https://raw.githubusercontent.com/alecthw/mmdb_china_ip_list/release/lite/Country.mmdb
curl -sfL -o files/etc/openclash/GeoSite.dat \
  https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat
curl -sfL -o files/etc/openclash/GeoIP.dat \
  https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat

ls -lh files/etc/openclash files/etc/openclash/core
