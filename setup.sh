#!/usr/bin/env bash
# bili-sub 幂等安装脚本：可反复执行
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
PY="${PYTHON:-python3}"
ok=0; warn=0; fail=0

say()  { printf '  %s\n' "$*"; }
step() { printf '\n[%s] %s\n' "$1" "$2"; }
pass() { printf '  PASS  %s\n' "$*"; ok=$((ok+1)); }
note() { printf '  WARN  %s\n' "$*"; warn=$((warn+1)); }
bad()  { printf '  FAIL  %s\n' "$*"; fail=$((fail+1)); }

step 1/6 "检查 python"
if command -v "$PY" >/dev/null 2>&1; then
  pass "$($PY -V 2>&1)"
else
  bad "找不到 $PY"; exit 1
fi

step 2/6 "校验源码语法"
if "$PY" -c "import ast;ast.parse(open('$DIR/bili_sub.py').read())" 2>/dev/null \
   && "$PY" -c "import ast;ast.parse(open('$DIR/bili_cookie_from_chrome.py').read())" 2>/dev/null; then
  pass "bili_sub.py / bili_cookie_from_chrome.py"
else
  bad "语法错误"; exit 1
fi

step 3/6 "安装命令到 $BIN_DIR"
install_one() {
  local name="$1" target="$2"
  local tmp; tmp="$(mktemp)"
  printf '#!/bin/sh\nexec %s %s "$@"\n' "$PY" "$target" > "$tmp"
  chmod 755 "$tmp"
  if [ -w "$BIN_DIR" ]; then
    mv -f "$tmp" "$BIN_DIR/$name" && pass "$BIN_DIR/$name"
  elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo mv -f "$tmp" "$BIN_DIR/$name" && sudo chmod 755 "$BIN_DIR/$name" && pass "$BIN_DIR/$name (sudo)"
  else
    note "$BIN_DIR 不可写且无免密 sudo；改用 ~/.local/bin"
    mkdir -p "$HOME/.local/bin"
    mv -f "$tmp" "$HOME/.local/bin/$name" && chmod 755 "$HOME/.local/bin/$name" \
      && pass "$HOME/.local/bin/$name（确认它在 PATH 里）"
  fi
}
install_one bili-sub "$DIR/bili_sub.py"
install_one bili-cookie "$DIR/bili_cookie_from_chrome.py"
chmod 755 "$DIR/bili_sub.py" "$DIR/bili_cookie_from_chrome.py" 2>/dev/null

step 4/6 "检查可选依赖 websocket-client（bili-cookie 需要）"
if "$PY" -c "import websocket" 2>/dev/null; then
  pass "已安装"
else
  if "$PY" -m pip install --quiet --break-system-packages websocket-client 2>/dev/null; then
    pass "已自动安装"
  else
    note "未安装；bili-cookie 不可用，可手工填 cookie"
  fi
fi

step 5/6 "检查 cookie"
COOKIE="$HOME/.config/bili-sub/cookie"
if [ -s "$COOKIE" ] && grep -q 'SESSDATA' "$COOKIE" 2>/dev/null; then
  chmod 600 "$COOKIE"
  pass "$COOKIE（$(wc -c <"$COOKIE") 字节）"
else
  note "没有有效 cookie：$COOKIE"
  say "取法："
  say "  a) 浏览器 F12 → Application → Cookies → bilibili.com → 复制 SESSDATA"
  say "     printf 'SESSDATA=%s' '你的值' > $COOKIE && chmod 600 $COOKIE"
  say "  b) 本机 Chromium 已登录 B 站并开了 9222：bili-cookie"
fi

step 6/6 "环境自检"
if command -v bili-sub >/dev/null 2>&1; then
  bili-sub --selftest && pass "自检通过" || note "自检有失败项，见上方逐项输出"
else
  "$PY" "$DIR/bili_sub.py" --selftest && pass "自检通过（用源码路径）" || note "自检有失败项"
fi

printf '\n==== 汇总: %d 通过, %d 警告, %d 失败 ====\n' "$ok" "$warn" "$fail"
printf '用法: bili-sub BV1xxxxxxxxx --fmt txt\n'
printf '文档: %s/AGENTS.md\n' "$DIR"
[ "$fail" -eq 0 ]
