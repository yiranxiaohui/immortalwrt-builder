# 设计：ImmortalWrt x86/64 云编译仓库（2026-08-01）

## 目标

一个公开 GitHub 仓库 `yiranxiaohui/immortalwrt-builder`，用 GitHub Actions（托管 runner，公开仓库免费）全量编译定制 ImmortalWrt x86/64 固件，产物发布到 Release。不在本地或服务器上跑任何构建。

## 需求（已确认）

- 预装 OpenClash（官方 feed 无，需克隆 vernesong/OpenClash）
- 预装官方 feed 的 AdGuard Home + LuCI，新设备默认 `AdGuard :53 → OpenClash :7874`；dnsmasq :54 负责 DHCP/局域网域名和直连故障备用
- 通用固件（不绑定现网关），默认 LAN IP 192.168.0.1
- PVE 虚拟机适配：磁盘分多大就用多大 → 首启自动扩容；预装 qemu-ga
- ext4 + EFI 镜像，kernel 32M + rootfs 1024M（基础值，扩容后无所谓）

## 架构

四类文件，全部声明式，改动即触发重编：

1. `.github/workflows/build.yml` — 流水线：腾磁盘 → 装依赖 → 浅克隆 v25.12.2 tag → diy-part1（克隆 OpenClash）→ feeds → 拷 config + diy-part2（files 覆盖层）→ defconfig → download → make → Release（tag=日期时间）
2. `config/x86_64.config` — 种子配置，defconfig 补全依赖
3. `scripts/diy-part{1,2}.sh` — 源码期钩子；part2 同时预下载 mihomo 内核与 GeoIP/GeoSite 数据进 `/etc/openclash`，使 OpenClash 离线可用
4. `files/etc/uci-defaults/{70-rootpt-resize,80-rootfs-resize}` — OpenWrt 官方 wiki 的两阶段首启扩容（parted 扩分区 → 重启 → resize2fs 扩文件系统 → 重启），标记文件写入 sysupgrade.conf 防止升级后重跑

## DNS 链路与安全

- `files/usr/share/adguardhome-builder/` 提供 YAML 模板和 Ruby 初始化器；`99-adguardhome-openclash` 只在设备首启生成 bcrypt 密码，不在固件构建期生成共享凭据。
- 使用 OpenClash 已依赖的 Ruby + ruby-yaml，以及 OpenWrt musl 的 bcrypt crypt；独立随机密码文件权限 `0600`。保留 AdGuard 官方低权限用户及 procd jail。
- AdGuard 不缓存 Fake-IP；dnsmasq 使用独立公共上游且不读取 WAN DNS，OpenClash 禁止本地 DNS 劫持。备用上游只在主上游失败时使用，明确是可用性优先的直连回退，不是防 DNS 泄漏方案。
- 已有 AdGuard、自定义 DNS 或已启用的 OpenClash 不自动接管；初始化标记、配置、凭据与数据通过 sysupgrade 保留。
- 集成测试在一次性 Alpine/musl 容器中验证真实 AdGuard 和模拟 OpenClash DNS 上游；不在本机构建固件，不把模拟测试当作真实路由器防火墙验证。
- 构建前运行测试，`make defconfig` 后断言所需软件包仍被选中；Release 附带 manifest 便于确认实际入镜像的软件包。

## 错误处理

- `make -j$(nproc)` 失败自动降级 `make -j1 V=s` 输出可读日志
- `make download` 后清除 <1KB 的残缺包并单线程重下
- 编译约 2-4 小时，runner 上限 6 小时，有余量

## 不做（YAGNI）

多 target、定时编译、第三方全家桶 feed、ccache 缓存。需要时各自一行可加。
