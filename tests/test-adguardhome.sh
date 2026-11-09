#!/bin/bash
# 使用与 OpenWrt 一样的 musl 验证 Ruby bcrypt；不在本机构建固件。
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
VERSION=0.107.78
curl -fsSL --retry 3 \
    "https://github.com/AdguardTeam/AdGuardHome/releases/download/v${VERSION}/AdGuardHome_linux_amd64.tar.gz" \
    -o "$TMP/adguardhome.tar.gz"
echo "2070f644644be8299232f4a7bff857036fb1423563c1bf8c787e07aaf4f88278  $TMP/adguardhome.tar.gz" | sha256sum -c -
tar -xzf "$TMP/adguardhome.tar.gz" -C "$TMP"
docker run --rm \
    -v "$ROOT:/repo:ro" -v "$TMP/AdGuardHome/AdGuardHome:/usr/local/bin/AdGuardHome:ro" \
    -e ADGUARDHOME_BINARY=/usr/local/bin/AdGuardHome \
    ruby:3.4-alpine@sha256:a28982cf8ed78eb0d222e51bc6788335d33ef191bfc6fc39da138577e611741d \
    sh -ec 'apk add --no-cache python3 py3-yaml dnsmasq >/dev/null; python3 /repo/tests/test_adguardhome.py'
