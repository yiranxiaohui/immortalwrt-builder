# 设计：ImmortalWrt x86/64 云编译仓库（2026-08-01）

## 目标

一个公开 GitHub 仓库 `yiranxiaohui/immortalwrt-builder`，用 GitHub Actions（托管 runner，公开仓库免费）全量编译定制 ImmortalWrt x86/64 固件，产物发布到 Release。不在本地或服务器上跑任何构建。

## 需求（已确认）

- 预装 OpenClash（官方 feed 无，需克隆 vernesong/OpenClash）
- 通用固件（不绑定现网关），默认 LAN IP 192.168.0.1
- PVE 虚拟机适配：磁盘分多大就用多大 → 首启自动扩容；预装 qemu-ga
- ext4 + EFI 镜像，kernel 32M + rootfs 1024M（基础值，扩容后无所谓）

## 架构

四类文件，全部声明式，改动即触发重编：

1. `.github/workflows/build.yml` — 流水线：腾磁盘 → 装依赖 → 浅克隆 v25.12.2 tag → diy-part1（克隆 OpenClash）→ feeds → 拷 config + diy-part2（files 覆盖层）→ defconfig → download → make → Release（tag=日期时间）
2. `config/x86_64.config` — 种子配置，defconfig 补全依赖
3. `scripts/diy-part{1,2}.sh` — 源码期钩子；part2 同时预下载 mihomo 内核与 GeoIP/GeoSite 数据进 `/etc/openclash`，使 OpenClash 离线可用
4. `files/etc/uci-defaults/{70-rootpt-resize,80-rootfs-resize}` — OpenWrt 官方 wiki 的两阶段首启扩容（parted 扩分区 → 重启 → resize2fs 扩文件系统 → 重启），标记文件写入 sysupgrade.conf 防止升级后重跑

## 错误处理

- `make -j$(nproc)` 失败自动降级 `make -j1 V=s` 输出可读日志
- `make download` 后清除 <1KB 的残缺包并单线程重下
- 编译约 2-4 小时，runner 上限 6 小时，有余量

## 不做（YAGNI）

多 target、定时编译、第三方全家桶 feed、ccache 缓存。需要时各自一行可加。
