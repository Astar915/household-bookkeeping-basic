"""Private Wi-Fi test launcher. No router changes or public tunnel."""
from __future__ import annotations

import argparse
import html
import ipaddress
import json
import os
import plistlib
import secrets
import socket
import ssl
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def lan_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            # Determines the chosen local interface without sending packets.
            sock.connect(("8.8.8.8", 80))
            address = sock.getsockname()[0]
            if not address.startswith("127."):
                return address
        except OSError:
            pass
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = info[4][0]
        if ipaddress.ip_address(address).is_private and not address.startswith("127."):
            return address
    raise RuntimeError("未找到 Wi-Fi/以太网地址。请先将电脑连接到与手机相同的网络。")


def prepare(folder: Path, address: str):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ca_key_file, ca_file = folder / "ca-key.pem", folder / "ca.pem"

    def write_private(path, data):
        with path.open("wb") as stream:
            os.chmod(path, 0o600)
            stream.write(data)

    def key_bytes(key):
        return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())

    existing_usable = ca_file.exists() and ca_key_file.exists()
    if existing_usable:
        try:
            x509.load_pem_x509_certificate(ca_file.read_bytes()).extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
        except (x509.ExtensionNotFound, ValueError):
            existing_usable = False
    if existing_usable:
        ca = x509.load_pem_x509_certificate(ca_file.read_bytes())
        ca_key = serialization.load_pem_private_key(ca_key_file.read_bytes(), None)
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Household Ledger Wi-Fi Test CA")])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
              .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
              .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                  data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                  encipher_only=False, decipher_only=False), critical=True)
              .sign(ca_key, hashes.SHA256()))
        write_private(ca_key_file, key_bytes(ca_key))
        ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, address)]))
            .issuer_name(ca.subject).public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address)),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    write_private(folder / "server-key.pem", key_bytes(leaf_key))
    (folder / "server.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    der = ca.public_bytes(serialization.Encoding.DER)
    (folder / "test-ca.cer").write_bytes(der)
    identifier = "local.householdledger.wifitest." + ca.fingerprint(hashes.SHA256()).hex()[:16]
    profile = {"PayloadContent": [{"PayloadCertificateFileName": "household-ledger-test.cer",
        "PayloadContent": der, "PayloadDescription": "此电脑的家庭记账 Wi-Fi 测试证书",
        "PayloadDisplayName": "Household Ledger Wi-Fi Test CA", "PayloadIdentifier": identifier + ".certificate",
        "PayloadType": "com.apple.security.root", "PayloadUUID": str(uuid.uuid5(uuid.NAMESPACE_URL, identifier + ".certificate")),
        "PayloadVersion": 1}], "PayloadDescription": "仅用于连接你自己的电脑测试家庭记账 PWA。测试结束可移除。",
        "PayloadDisplayName": "家庭记账 Wi-Fi 测试", "PayloadIdentifier": identifier,
        "PayloadRemovalDisallowed": False, "PayloadType": "Configuration", "PayloadUUID": str(uuid.uuid5(uuid.NAMESPACE_URL, identifier)),
        "PayloadVersion": 1}
    (folder / "iphone-test.mobileconfig").write_bytes(plistlib.dumps(profile))
    invite_file = folder / "invitation.txt"
    if not invite_file.exists():
        write_private(invite_file, secrets.token_urlsafe(24).encode())
    return invite_file.read_text().strip(), ca.fingerprint(hashes.SHA256()).hex()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HouseholdBookkeeping" / "MobileTest"
    address = args.address or lan_address()
    # A running launcher owns both ports; reuse its instructions instead of starting two servers.
    try:
        with socket.create_connection(("127.0.0.1", 8766), timeout=1):
            if not args.no_browser:
                webbrowser.open("http://127.0.0.1:8766")
            return 0
    except OSError:
        pass
    invite, fingerprint = prepare(folder, address)
    app_url, help_url = f"https://{address}:8443", f"http://{address}:8766"
    info = {"appUrl": app_url, "setupUrl": help_url, "fingerprint": fingerprint,
            "dataDirectory": str(PROJECT / "data" / "web"), "pid": os.getpid()}
    (folder / "status.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.prepare_only:
        print(json.dumps(info, ensure_ascii=True))
        return 0
    os.environ.update(HOUSEHOLD_WEB_ALLOW_REMOTE="1", HOUSEHOLD_WEB_INVITE_CODE=invite,
                      HOUSEHOLD_WEB_PUBLIC_ORIGIN=app_url, HOUSEHOLD_WEB_ALLOW_LOCAL_API="1",
                      HOUSEHOLD_WEB_TEST_CA=str(folder / "test-ca.cer"))
    from bookkeeping.web import BookkeepingWebServer
    server = BookkeepingWebServer(("0.0.0.0", 8443), PROJECT / "data" / "web", app_url)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(folder / "server.pem", folder / "server-key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)

    class Help(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_GET(self):
            if self.path == "/iphone-test.mobileconfig":
                body = (folder / "iphone-test.mobileconfig").read_bytes()
                content_type = "application/x-apple-aspen-config"
                self.send_response(200)
                self.send_header("Content-Disposition", 'attachment; filename="iphone-test.mobileconfig"')
            elif self.path in {"/", "/index.html"}:
                local = ipaddress.ip_address(self.client_address[0]).is_loopback
                invitation = '<section><h2>直接使用 GitHub 登录</h2><p>无需注册软件账号，也不需要邀请码。点击应用中的“使用 GitHub 登录”，在 GitHub 页面确认授权后返回，程序会自动打开你的账本。</p><p>已有旧版账号可展开“迁移原账本”，验证原账号后关联 GitHub，保留已有数据。</p></section>'
                body = ('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>家庭记账 · iPhone 测试安装</title><style>body{font:17px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f6fa;color:#17223b;max-width:780px;margin:36px auto;padding:0 22px}section{background:white;padding:22px;border-radius:24px;margin:22px 0}a{color:#1761d5}code{overflow-wrap:anywhere}h1{letter-spacing:-1px}li{margin:14px 0}.button{display:inline-block;padding:12px 22px;background:#1761d5;color:white;border-radius:16px;text-decoration:none}</style><h1>把家庭记账装进 iPhone</h1><p>电脑可连接本手机的个人热点，也可与手机连接同一局域网；保持热点和电脑服务开启。此测试服务没有公网入口。</p><section><h2>1 · 手机打开安装说明</h2><p>在 iPhone 的 Safari 中输入：<br><strong>''' + help_url + '''</strong></p><p>若打不开，请检查 Windows 防火墙对 Python 的“专用网络”访问，以及路由器是否隔离访客设备。不需要关闭防火墙。</p></section><section><h2>2 · 安装此电脑的测试证书（只需一次）</h2><ol><li><a href="/iphone-test.mobileconfig">下载家庭记账测试证书描述文件</a></li><li>打开 iPhone「设置 → 通用 → VPN 与设备管理」，选择「家庭记账 Wi-Fi 测试」并安装。</li><li>打开「设置 → 通用 → 关于本机 → 证书信任设置」，为 Household Ledger Wi-Fi Test CA 开启完全信任。</li></ol><p>只安装你自己电脑生成的这份证书。完成信任后再打开应用；不要跳过浏览器的证书警告。测试结束可在设备管理中删除此描述文件。</p><details><summary>核对证书 SHA-256 指纹</summary><code>''' + fingerprint + '''</code></details></section><section><h2>3 · 打开应用并添加到主屏幕</h2><a class="button" href="''' + app_url + '''">打开家庭记账</a><p>地址：''' + app_url + '''</p><p>使用 GitHub 登录。然后 Safari「分享 → 添加到主屏幕」，启用“作为 Web App 打开”（若出现），点“添加”。</p><p>Skill 在「更多 → 设置与 Agent Skill」直接粘贴、编辑并保存，不需要选择文件。</p></section>''' + invitation + '''<section><h2>你的账本在哪里？</h2><p>手机测试使用独立账号账本，不会直接修改桌面账本。要使用已有数据，请先从桌面上传云端备份，再在手机连接同一 GitHub/Gitee 并恢复；连接成功本身不会覆盖现有云备份。也可以下载同步包后导入。</p><p>离线可填写手动记录，恢复与电脑的连接后续传；AI、报表更新、云备份需要电脑服务在线。更换热点或 Wi-Fi 导致电脑地址变化时，重新运行启动入口并查看新地址。</p></section></html>''').encode("utf-8")
                content_type = "text/html; charset=utf-8"
                self.send_response(200)
            else:
                self.send_error(404)
                return
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    help_server = ThreadingHTTPServer(("0.0.0.0", 8766), Help)
    threading.Thread(target=help_server.serve_forever, daemon=True).start()
    if not args.no_browser:
        webbrowser.open("http://127.0.0.1:8766")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        help_server.shutdown()
        help_server.server_close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        log = PROJECT / "data" / "web" / "startup-error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"手机测试服务未能启动。请查看：\n{log}", "家庭记账", 0x10)
        raise
