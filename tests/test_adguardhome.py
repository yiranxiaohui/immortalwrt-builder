"""Run in tests/test-adguardhome.sh's disposable Alpine/musl container."""
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "files/usr/share/adguardhome-builder/adguardhome.yaml"
INITIALIZER = ROOT / "files/usr/share/adguardhome-builder/initialize.rb"
DEFAULTS = ROOT / "files/etc/uci-defaults/99-adguardhome-openclash"
AGH = os.environ["ADGUARDHOME_BINARY"]


class AdGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "adguardhome.yaml"
        self.credentials = self.root / "credentials.txt"

    def generate(self):
        return subprocess.run(
            ["ruby", str(INITIALIZER), str(TEMPLATE), str(self.config), str(self.credentials)],
            capture_output=True, check=True,
        )

    def test_credentials_and_config(self):
        result = self.generate()
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        config = yaml.safe_load(self.config.read_text())
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)
        self.assertEqual(config["users"][0]["name"], "admin")
        self.assertTrue(config["users"][0]["password"].startswith("$2a$10$"))
        self.assertEqual(config["dns"]["upstream_dns"][0], "127.0.0.1:7874")
        self.assertEqual(config["dns"]["fallback_dns"], ["127.0.0.1:54"])
        self.assertFalse(config["dns"]["cache_enabled"])
        self.assertFalse(config["dhcp"]["enabled"])
        before = self.config.read_bytes(), self.credentials.read_bytes()
        retry = subprocess.run(
            ["ruby", str(INITIALIZER), str(TEMPLATE), str(self.config), str(self.credentials)],
            capture_output=True,
        )
        self.assertNotEqual(retry.returncode, 0)
        self.assertEqual(before, (self.config.read_bytes(), self.credentials.read_bytes()))
        other = self.root / "other.yaml"
        subprocess.run(
            ["ruby", str(INITIALIZER), str(TEMPLATE), str(other), str(self.root / "other.txt")],
            check=True,
        )
        self.assertNotEqual(config["users"], yaml.safe_load(other.read_text())["users"])
        work = self.root / "data"
        work.mkdir()
        subprocess.run([AGH, "--check-config", "-c", str(self.config), "-w", str(work)], check=True)

    def defaults(self, overrides=None, existing=None, invalid=False, image_build=False):
        # Rewrite absolute paths into a sandbox; mock only UCI/init/logger and the
        # check-config call. The actual Ruby generator still runs on musl.
        root = self.root / "router"
        root.mkdir(exist_ok=True)
        (root / "etc").mkdir(exist_ok=True)
        (root / "usr/share").mkdir(parents=True, exist_ok=True)
        shutil.copytree(TEMPLATE.parent, root / "usr/share/adguardhome-builder", dirs_exist_ok=True)
        state = {"openclash.config.enable": "0", "dhcp.@dnsmasq[0].port": "53"}
        state.update(overrides or {})
        statefile = root / "state.json"
        statefile.write_text(json.dumps(state))
        if existing:
            target = root / existing.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("user-owned configuration")
        bin_dir = root / "bin"
        bin_dir.mkdir(exist_ok=True)
        uci = bin_dir / "uci"
        uci.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p = Path(os.environ['UCI_STATE'])
s = json.loads(p.read_text())
a = [v for v in sys.argv[1:] if v != '-q']
if a[0] == 'get':
    if a[1] not in s: sys.exit(1)
    print(s[a[1]])
elif a[0] in ('set', 'add_list'):
    k, v = a[1].split('=', 1)
    if a[0] == 'set': s[k] = v
    else: s[k] = (s.get(k, '') + ' ' + v).strip()
    p.write_text(json.dumps(s))
elif a[0] == 'delete':
    s.pop(a[1], None)
    p.write_text(json.dumps(s))
elif a[0] != 'commit': sys.exit(2)
''')
        uci.chmod(0o755)
        for path, body in [(bin_dir / "logger", "exit 0"),
                           (root / "etc/init.d/adguardhome", "exit 0"),
                           (root / "usr/bin/AdGuardHome", f"exit {1 if invalid else 0}")]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/bin/sh\n" + body + "\n")
            path.chmod(0o755)
        script = root / "defaults.sh"
        script.write_text(DEFAULTS.read_text().replace("/etc/", f"{root}/etc/")
                          .replace("/usr/", f"{root}/usr/"))
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", UCI_STATE=str(statefile))
        if image_build:
            env["IPKG_INSTROOT"] = str(root)
        result = subprocess.run(["/bin/sh", str(script)], env=env, capture_output=True)
        return root, state, json.loads(statefile.read_text()), result, script, env

    def test_first_boot_and_idempotence(self):
        root, _, state, result, script, env = self.defaults()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state["dhcp.@dnsmasq[0].port"], "54")
        self.assertEqual(state["dhcp.@dnsmasq[0].server"], "223.5.5.5 119.29.29.29")
        self.assertEqual(state["dhcp.@dnsmasq[0].noresolv"], "1")
        self.assertEqual(state["dhcp.lan.dhcp_option"], "6,0.0.0.0")
        self.assertEqual(state["dhcp.lan.dns_service"], "1")
        self.assertEqual(state["openclash.config.enable_redirect_dns"], "0")
        self.assertEqual(state["openclash.config.enable"], "0")
        credentials = root / "etc/adguardhome-admin.txt"
        original = credentials.read_bytes()
        subprocess.run(["/bin/sh", str(script)], env=env, check=True)
        self.assertEqual(original, credentials.read_bytes())
        self.assertEqual(state, json.loads((root / "state.json").read_text()))

    def test_resume_interrupted_boot(self):
        root, _, state, result, script, env = self.defaults()
        self.assertEqual(result.returncode, 0, result.stderr)
        credentials = (root / "etc/adguardhome-admin.txt").read_bytes()
        (root / "etc/adguardhome-builder.initialized").unlink()
        (root / "etc/adguardhome-builder.pending").touch()
        subprocess.run(["/bin/sh", str(script)], env=env, check=True)
        self.assertEqual(credentials, (root / "etc/adguardhome-admin.txt").read_bytes())
        self.assertEqual(state, json.loads((root / "state.json").read_text()))
        self.assertFalse((root / "etc/adguardhome-builder.pending").exists())
        self.assertTrue((root / "etc/adguardhome-builder.initialized").exists())

    def test_preserve_existing_config(self):
        for existing in ("/etc/adguardhome/adguardhome.yaml", "/etc/adguardhome.yaml"):
            with self.subTest(existing=existing):
                root, before, after, result, _, _ = self.defaults(existing=existing)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(before, after)
                self.assertFalse((root / "etc/adguardhome-admin.txt").exists())

    def test_preserve_custom_dns(self):
        cases = [{"openclash.config.enable": "1"}, {"dhcp.@dnsmasq[0].server": "10.0.0.1"},
                 {"dhcp.@dnsmasq[0].port": "5353"}, {"dhcp.lan.dhcp_option": "6,10.0.0.1"},
                 {"dhcp.lan.dns": "fd00::1"}]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                root, before, after, result, _, _ = self.defaults(overrides=overrides)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(before, after)
                self.assertFalse((root / "etc/adguardhome-admin.txt").exists())

    def test_validation_failure_keeps_dnsmasq(self):
        root, before, after, result, _, _ = self.defaults(invalid=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, after)
        self.assertFalse((root / "etc/adguardhome/adguardhome.yaml").exists())

    def test_no_credentials_during_image_build(self):
        root, before, after, result, _, _ = self.defaults(image_build=True)
        self.assertNotEqual(result.returncode, 0)  # keep uci-defaults for real boot
        self.assertEqual(before, after)
        self.assertFalse((root / "etc/adguardhome-admin.txt").exists())

    def launch(self, command, name):
        log = (self.root / f"{name}.log").open("w")
        self.addCleanup(log.close)
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        def stop():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        self.addCleanup(stop)
        return process

    def query(self, name, tcp=False, ipv6=False, qtype=1):
        question = b"".join(bytes([len(label)]) + label.encode() for label in name.split('.')) + b"\0"
        packet = struct.pack("!6H", 1234, 0x100, 1, 0, 0, 0) + question + struct.pack("!HH", qtype, 1)
        with socket.socket(socket.AF_INET6 if ipv6 else socket.AF_INET,
                           socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            sock.connect(("::1" if ipv6 else "127.0.0.1", 53))
            if tcp:
                sock.sendall(struct.pack("!H", len(packet)) + packet)
                length = struct.unpack("!H", sock.recv(2))[0]
                result = b""
                while len(result) < length:
                    result += sock.recv(length - len(result))
            else:
                sock.send(packet)
                result = sock.recv(4096)
        self.assertEqual(result[3] & 15, 0)
        self.assertGreater(struct.unpack("!H", result[6:8])[0], 0)
        if qtype == 12:
            return result
        return socket.inet_ntoa(result[-4:])

    def test_live_dns_and_auth(self):
        self.generate()
        config = yaml.safe_load(self.config.read_text())
        # No external network or downloaded blocklist needed for integration tests.
        config['filters'] = []
        config['user_rules'] = ['||blocked.example^']
        self.config.write_text(yaml.safe_dump(config))
        work = self.root / "data"
        work.mkdir()
        common = ["dnsmasq", "--keep-in-foreground", "--conf-file=/dev/null", "--no-resolv",
                  "--no-hosts", "--bind-interfaces", "--listen-address=127.0.0.1", "--user=root",
                  "--log-queries", "--log-facility=-"]
        upstream = self.launch(common + ["--port=7874", "--address=/example/198.18.0.10"], "upstream")
        self.launch(common + ["--port=54", "--address=/example/203.0.113.10",
                              "--address=/lan/192.168.0.25", "--ptr-record=25.0.168.192.in-addr.arpa,host.lan"], "fallback")
        self.launch([AGH, "-c", str(self.config), "-w", str(work), "--no-check-update"], "adguard")
        url = "http://127.0.0.1:3000/control/status"
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=0.2)
            except urllib.error.HTTPError as error:
                self.assertEqual(error.code, 401)
                error.close()
                break
            except OSError:
                time.sleep(0.1)
            else:
                self.fail("management API must require authentication")
        else:
            self.fail("AdGuard Home did not start")
        password = self.credentials.read_text().split('Password: ', 1)[1].strip()
        request = urllib.request.Request(url, headers={"Authorization": "Basic " +
            base64.b64encode(f"admin:{password}".encode()).decode()})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 200)  # proves Go accepts musl bcrypt hash
        self.assertEqual(self.query("normal.example"), "198.18.0.10")
        self.assertEqual(self.query("normal.example", tcp=True), "198.18.0.10")
        self.assertEqual(self.query("normal.example", ipv6=True), "198.18.0.10")
        self.assertEqual(self.query("host.lan"), "192.168.0.25")
        self.assertIn(b'\x04host\x03lan\x00', self.query("25.0.168.192.in-addr.arpa", qtype=12))
        self.assertEqual(self.query("blocked.example"), "0.0.0.0")
        self.assertNotIn("normal.example", (self.root / "fallback.log").read_text())
        self.assertNotIn("blocked.example", (self.root / "upstream.log").read_text())
        self.assertNotIn("blocked.example", (self.root / "fallback.log").read_text())
        upstream.terminate()
        upstream.wait(timeout=5)
        self.assertEqual(self.query("normal.example"), "203.0.113.10")
        self.assertEqual(self.query("blocked.example"), "0.0.0.0")
        self.launch(common + ["--port=7874", "--address=/example/198.18.0.11"], "recovered")
        for _ in range(20):
            if self.query("normal.example") == "198.18.0.11":
                break
            time.sleep(0.1)
        else:
            self.fail("upstream recovery must not use cached fallback/Fake-IP answers")


if __name__ == "__main__":
    unittest.main(verbosity=2)
