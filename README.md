# immortalwrt-builder

ImmortalWrt x86/64 云编译（GitHub Actions），面向 PVE 虚拟机 / 通用 x86 软路由。

## 固件特性

- 基于 `immortalwrt/immortalwrt` 分支 `openwrt-25.12`，target `x86/64`
- ext4 + EFI/BIOS combined 镜像，kernel 32M + rootfs 1024M
- **首次开机自动把 rootfs 扩容到整块磁盘**（PVE 分多大盘就用多大，过程中自动重启两次）
- 预装 OpenClash（内置 mihomo 内核 + GeoIP/GeoSite/Country.mmdb，离线可用）
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

## 定制点

| 想改什么 | 改哪里 |
|---------|--------|
| 增删软件包 | `config/x86_64.config` |
| 加第三方插件源码 | `scripts/diy-part1.sh` |
| 预置文件 / 默认配置 | `files/`（原样进 rootfs）+ `scripts/diy-part2.sh` |
| 换分支 / 源 | `.github/workflows/build.yml` 顶部 env |
