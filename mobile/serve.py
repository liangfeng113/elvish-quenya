#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在局域网里把手机版服务出去，iPhone 用 Safari 打开即可。

用法: python mobile/serve.py [端口]
      QUENYA_PORT=8123 python mobile/serve.py

只监听局域网，不往公网暴露任何东西。
"""
import http.server
import mimetypes
import os
import socket
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "web")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("QUENYA_PORT", "8123"))

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("application/javascript", ".js")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.1.1", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    if not os.path.isdir(ROOT):
        sys.exit("找不到 %s" % ROOT)
    ip = lan_ip()
    print("昆雅手机版已启动，iPhone 的 Safari 打开：")
    print("    http://%s:%d/" % (ip, PORT))
    print("（手机和这台电脑要在同一个 Wi-Fi 下；Ctrl+C 停止）")
    sys.stdout.flush()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")


if __name__ == "__main__":
    main()
