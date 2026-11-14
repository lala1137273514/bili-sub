#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从本机已开调试端口的 Chromium 里自动抠 B 站 cookie，写入 ~/.config/bili-sub/cookie

前置：Chromium 以 --remote-debugging-port=9222 启动，且你已在该实例里登录 bilibili.com
用法：bili-cookie [--port 9222] [--out ~/.config/bili-sub/cookie] [--check]
"""
import argparse
import json
import os
import sys
import time
import urllib.request

try:
    import websocket  # websocket-client
except ImportError:
    print("需要 websocket-client：pip install --break-system-packages websocket-client", file=sys.stderr)
    sys.exit(2)


def cdp_new_tab(port, url):
    req = urllib.request.Request("http://127.0.0.1:%d/json/new?%s" % (port, url), method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode())


def grab(port, wait=6.0):
    tab = cdp_new_tab(port, "https://www.bilibili.com/")
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
    seq = [0]

    def call(method, params=None):
        seq[0] += 1
        ws.send(json.dumps({"id": seq[0], "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == seq[0]:
                return msg

    call("Network.enable")
    time.sleep(wait)
    res = call("Network.getAllCookies")
    cookies = (res.get("result") or {}).get("cookies") or []
    ws.close()
    pairs = {}
    for c in cookies:
        dom = c.get("domain", "")
        if "bilibili" in dom and c.get("name"):
            pairs[c["name"]] = c["value"]
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--out", default=os.path.expanduser("~/.config/bili-sub/cookie"))
    ap.add_argument("--wait", type=float, default=6.0, help="打开页面后等待秒数")
    ap.add_argument("--check", action="store_true", help="只检查是否已登录")
    args = ap.parse_args()

    try:
        pairs = grab(args.port, args.wait)
    except Exception as e:
        print("CDP 连接失败（Chromium 是否带 --remote-debugging-port 启动？）: %s" % e, file=sys.stderr)
        sys.exit(2)

    has = "SESSDATA" in pairs
    print("bilibili cookie: %d 个 | SESSDATA: %s" % (len(pairs), "有" if has else "没有（该实例未登录 B 站）"))
    if args.check:
        sys.exit(0 if has else 1)
    if not has:
        print("请先在端口 %d 的浏览器里登录 bilibili.com 再重跑" % args.port, file=sys.stderr)
        sys.exit(1)

    keep = [k for k in ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "buvid3", "buvid4") if k in pairs]
    cookie = "; ".join("%s=%s" % (k, pairs[k]) for k in keep)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(cookie)
    os.chmod(args.out, 0o600)
    print("已写入 %s（%d 个字段）" % (args.out, len(keep)))


if __name__ == "__main__":
    main()
