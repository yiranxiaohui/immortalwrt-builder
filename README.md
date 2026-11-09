# immortalwrt-builder

ImmortalWrt x86/64 云编译（GitHub Actions），面向 PVE 虚拟机 / 通用 x86 软路由。

## 固件特性

- 基于 `immortalwrt/immortalwrt` 正式版 `v25.12.2`（tag 锁定，feeds 同步锁定），target `x86/64`
- ext4 + EFI/BIOS combined 镜像，kernel 32M + rootfs 1024M
- **首次开机自动把 rootfs 扩容到整块磁盘**（PVE 分多大盘就用多大，过程中自动重启两次）
- 预装 OpenClash（内置 mihomo 内核 + GeoIP/GeoSite/Country.mmdb，离线可用）
- 预装 AdGuard Home + LuCI，首次开机配置 `AdGuard Home → OpenClash` DNS 链路，带独立随机管理密码
- 预装 qemu-ga（PVE 面板可见 IP / 干净关机）、LuCI 中文、ttyd、htop、parted
- 默认 LAN IP `192.168.0.1`

## 用法

- **触发编译**：Actions → Build ImmortalWrt x86_64 → Run workflow；或直接改 `config/`、`scripts/`、`files/` 后 push
- **产物**：编译完成后自动发布 Release（tag 为日期时间），下载 `*combined-efi.img.gz`
- **PVE 导入**：
  ```bash
  qm create <vmid> --name immortalwrt --cores 4 --memory 2048 --net0 virtio,bridge=vmbr0 --bios ovmf --efidisk0 local-lvm:0 --machine q35
  gunzip immortalwrt-*combined-efi.img.gz
  qm importdisk <vmid> immortalwrt-*combined-efi.img local-lvm
  qm set <vmid> --scsi0 local-lvm:vm-<vmid>-disk-1 --boot order=scsi0 --agent 1
  qm resize <vmid> scsi0 +8G   # 随意扩，首启自动占满
  ```

## AdGuard Home → OpenClash

全新刷机（或恢复出厂）后自动配置：

```text
客户端 IPv4 / IPv6 DNS
  └─ AdGuard Home :53（广告过滤、查询统计，不缓存 Fake-IP）
       ├─ 普通查询 → OpenClash 127.0.0.1:7874 → OpenClash 配置的公共 DNS
       ├─ .lan / 私网 PTR → dnsmasq 127.0.0.1:54（局域网主机名）
       └─ 主上游失败 → dnsmasq 127.0.0.1:54 → 223.5.5.5 / 119.29.29.29
```

- **AdGuard 管理界面**：`http://192.168.0.1:3000`（修改 LAN IP 后使用新地址），用户名 `admin`。通过路由器 SSH 或 LuCI 的终端查看 `/etc/adguardhome-admin.txt` 获取每台设备首次开机独立生成的密码；文件仅 root 可读，不要公开。密码不是 LuCI 密码。登录后可修改密码，并删除该初始凭据文件。
- **LuCI → 服务 → AdGuard Home**：启停服务、查看版本和运行状态；过滤规则和查询日志在上述 `:3000` 管理界面。
- **OpenClash**：仍需自己导入订阅/配置并手动启用。默认 Fake-IP 模式；DNS 端口固定为 `7874`，本地 DNS 劫持为**停用**，自定义上游 DNS 已开启（使用插件内置公共 DNS），不追加 WAN/系统 DNS。不要改成“Dnsmasq 转发”或“防火墙转发”，否则可能绕过 AdGuard 或形成回环。
- **故障备用**：未启用 OpenClash、启动中或其 DNS 查询失败时，AdGuard 使用备用 DNS；不是同时向两个上游抢答。最多等待主上游超时约 2 秒。这是**可用性优先的直连回退**，不是防 DNS 泄漏/断网保护；代理不可用时，备用 DNS 也不能保证被代理的网站可访问。
- **dnsmasq 仍提供 DHCP**：仅 DNS 端口改成 `54`，上游固定为独立公共 DNS，不指回 AdGuard/OpenClash；DHCPv4 与 IPv6 RA/DHCPv6 宣告路由器自身的 DNS。没有新增 WAN 放行或强制劫持规则。使用自带 DoH/DoT、手工指定其他 DNS 的客户端不保证经过过滤。
- **广告列表**：默认启用 AdGuard DNS filter，首次联网后下载；离线新刷机时没有内置完整广告列表，可在面板中检查更新结果。DNS 级过滤无法去除所有同域广告。
- **持久化**：配置、过滤列表和日志保存在 `/etc/adguardhome/`，查询日志与统计保留 24 小时。sysupgrade 保留配置时会保留该目录、初始密码文件和初始化标记；备份文件包含敏感信息，应妥善保管。

### 升级已有设备

已有 AdGuard 配置、已启用的 OpenClash、自定义 dnsmasq 上游/端口或 LAN DNS 宣告时，**不会自动改写现网 DNS**，只是增加软件包。确认备份后，可通过界面手动按上图接线；不要为了触发自动初始化而删除原配置。自动设置跳过的原因可用 `logread -e adguardhome-builder` 查看。

导入的 OpenClash 配置及自定义覆写中的所有 DNS 项（尤其 `nameserver-policy`、节点域名解析）都不能再指向路由器 `:53` / AdGuard 或 `:7874` 自身，否则可能回环；上游应使用公共 DNS。更改代理模式或开启 TUN 后，应重新检查 DNS 查询是否仍出现在 AdGuard 日志中。

### 快速验证

1. 新设备开机、扩容重启完成后，检查 AdGuard `:3000` 可登录；客户端 DNS 应为路由器地址。
2. 未启用 OpenClash 时，测试普通域名仍能解析，AdGuard 日志显示备用 `127.0.0.1:54`。
3. 导入配置并启动 OpenClash 后，再查询普通域名，日志应显示上游 `127.0.0.1:7874`；Fake-IP 模式可返回 `198.18.x.x`。
4. 测试局域网 `.lan` 主机名、广告域名拦截，以及关闭 OpenClash 后备用解析是否恢复。

**不要只停用 AdGuard**：它是客户端的 `:53` DNS 入口。若要撤销链路，先停止 AdGuard，再把 dnsmasq DNS 端口恢复为 `53` 并重启 dnsmasq；需要代理 DNS 时，再在 OpenClash 启用其原生 DNS 转发模式。

## 验证开发改动

```bash
bash -n scripts/diy-part1.sh scripts/diy-part2.sh tests/test-adguardhome.sh
shellcheck files/etc/uci-defaults/99-adguardhome-openclash tests/test-adguardhome.sh
bash tests/test-adguardhome.sh  # 需要 Docker 权限和网络，不编译固件
```

集成测试使用一次性 Alpine/musl 容器和经 SHA-256 校验的 `AdGuard Home v0.107.78`，验证首启设置、配置保留、密码权限/认证、DNS TCP/UDP/IPv6 转发、广告拦截、局域网解析和故障备用。完整固件只在 GitHub Actions 构建，仍需刷入测试机验证真实 OpenClash、防火墙及 DHCP 行为。

## 定制点

| 想改什么 | 改哪里 |
|---------|--------|
| 增删软件包 | `config/x86_64.config` |
| 加第三方插件源码 | `scripts/diy-part1.sh` |
| 预置文件 / 默认配置 | `files/`（原样进 rootfs）+ `scripts/diy-part2.sh` |
| 升级版本 / 换分支 / 源 | `.github/workflows/build.yml` 顶部 env（`REPO_BRANCH` 可填 tag 或分支） |
