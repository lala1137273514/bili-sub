# bili-sub

B 站字幕一条命令拉下来。**CC 字幕 / AI 字幕**（中文、English、日本語、Español、العربية、Português、ภาษาไทย、Bahasa Indonesia 共 8 轨），输出 `srt` / `txt` 等 10 种格式。

不需要录屏、不需要浏览器插件、不需要语音转写。唯一前提：一条有效的 `SESSDATA`。

```bash
bili-sub BV1MsnG6TEf3                      # 单视频 → srt + txt
bili-sub BV1MsnG6TEf3 --list               # 看有几轨字幕
bili-sub --up 324213598 --limit 50         # UP 主空间批量
bili-sub --up 324213598 --limit 50 --drive # 导完归档到你挂载的网盘
```

- 纯标准库，零依赖（`bili-cookie` 除外）
- 支持 BV 号 / av 号 / 完整 URL / `b23.tv` 短链 / 分P
- 支持文件批量、stdin 管道、UP 主空间全量翻页
- `--drive` 按 UP 主自动建目录，生成 `_manifest.json` 与合并稿

---

## 安装

```bash
git clone https://github.com/<you>/bili-sub.git
cd bili-sub
bash setup.sh          # 幂等：装命令、查依赖、查 cookie、跑自检
```

`setup.sh` 会把 `bili-sub` 和 `bili-cookie` 两个命令装到 `/usr/local/bin`（无权限则退到 `~/.local/bin`）。

手动安装也可以：

```bash
chmod +x bili_sub.py bili_cookie_from_chrome.py
ln -s "$PWD/bili_sub.py" ~/.local/bin/bili-sub
ln -s "$PWD/bili_cookie_from_chrome.py" ~/.local/bin/bili-cookie
pip install websocket-client   # 只有 bili-cookie 需要
```

---

## cookie（唯一的门槛）

B 站的字幕接口 `x/player/wbi/v2` **只对登录用户下发字幕轨**，未登录恒返回 `subtitles: []`。所以要一条 `SESSDATA`。

三种来源，优先级从高到低：

1. `--cookie 'SESSDATA=xxx'` / `--cookie-file path`
2. `~/.config/bili-sub/cookie`（建议 `chmod 600`）
3. 环境变量 `BILI_COOKIE` / `BILI_SESSDATA`

**手工取**：浏览器打开 bilibili.com → F12 → `Application → Storage → Cookies → https://www.bilibili.com` → 复制 `SESSDATA` 的 Value（保留 `%2C` 编码，别解码）。

> 控制台 `document.cookie` 读不到它，`SESSDATA` 是 HttpOnly。

**自动取**（本机 Chromium 已登录 B 站、且带 `--remote-debugging-port=9222` 启动时）：

```bash
bili-cookie --check    # 检查有没有登录态
bili-cookie            # 有就写进 ~/.config/bili-sub/cookie（600）
bili-cookie --port 9333
```

过期了（返回 `code=-101`）就重新取一次。

---

## 用法

```bash
# 语言
bili-sub BV1xxx                        # 默认中文（ai-zh）
bili-sub BV1xxx -l en,ja               # 多语言
bili-sub BV1xxx --all                  # 8 轨全要

# 格式（详见下表）
bili-sub BV1xxx --fmt txt              # 只要纯文本
bili-sub BV1xxx --fmt srt,vtt,ass      # 字幕类
bili-sub BV1xxx --fmt srt,txt,json,jsonl,vtt,ass,lrc,csv,md,para

# 批量
bili-sub -f list.txt -o out            # 文件：每行一个 BV / URL
cat list.txt | bili-sub -              # 管道

# UP 主空间
bili-sub --up 1892407222 --limit 100
bili-sub 'https://space.bilibili.com/1892407222' --limit 100
bili-sub --up 1892407222 --limit 100 --order click    # 按播放量排序

# 分P
bili-sub 'https://www.bilibili.com/video/BV1xxx/?p=2'

# 归档到网盘（rclone mount / 任意本地目录）
bili-sub --up 1892407222 --limit 100 --drive
bili-sub --up 1892407222 --limit 100 --drive /mnt/nas/B站   # 自定义根目录

# 环境自检
bili-sub --selftest
```

---

## 输出格式

`--fmt` 逗号分隔，默认 `srt,txt`。

| 格式 | 后缀 | 用途 |
|---|---|---|
| `srt` | `.srt` | 播放器 / 剪辑 / 平台上传，最通用 |
| `vtt` | `.vtt` | HTML5 `<track>`、网页播放器 |
| `ass` | `.ass` | 带样式，B站/压制/剪辑 |
| `txt` | `.txt` | 纯文本，喂 LLM、检索、写作素材 |
| `para` | `.para.txt` | 分段纯文本，碎句合并成自然段 |
| `md` | `.md` | Markdown + `[mm:ss.cc]` 时间锚点 |
| `lrc` | `.lrc` | 歌词式滚动 |
| `csv` | `.csv` | `from,to,content` 三列，表格分析 |
| `jsonl` | `.jsonl` | 一行一条，管道友好 |
| `json` | `.json` | 完整 `[{from,to,content}]` |

同一视频（1036 条字幕）实测体积，以 `txt` 为 1.00x：

| 格式 | 相对体积 |
|---|---|
| `para` | 0.92x |
| `txt` | 1.00x |
| `lrc` | 1.86x |
| `md` | 2.47x |
| `csv` | 2.48x |
| `srt` / `vtt` | 4.01x |
| `jsonl` | 4.98x |
| `ass` | 5.36x |
| `json` | 9.98x |

**喂模型用 `txt`（或 `para`），要时间定位用 `md`，`srt` 只给播放器。** `srt` 喂模型是白烧 4 倍 token，`ass`/`json` 更亏。

---

## 网盘归档

`--drive` 启动后按视频 `owner.name` 建目录：

```
<drive 根>/
  <UP昵称>/
    _manifest.json          [{idx,bvid,aid,title,length,chars,files[]}, ...]
    _合集_全部字幕.txt       所有 txt 拼接，带 ===== 分隔头
    <标题>_(BV号)_ai-zh.srt
    <标题>_(BV号)_ai-zh.txt
```

文件名里 `(BV号)` 是唯一锚点，标题改名不影响检索。

> 用 rclone mount 时注意 `--vfs-write-back`：写完是异步上传的，立刻 `rclone lsf` 会看到空，等 `to upload 0` 才是真完成。

---

## 原理

```
BV号 ──► x/web-interface/view        → aid / cid / pages[]
     ──► x/web-interface/nav         → wbi_img（混密钥源）
     ──► x/player/wbi/v2  (wbi签名)  → subtitle.subtitles[]   ← 需要登录 cookie
     ──► aisubtitle.hdslb.com/...    → {"body":[{from,to,content},...]}
     ──► 本地转 srt / txt / ...
```

**wbi 签名**：`img_key + sub_key` 拼成 64 字符，按固定表 `MIXIN_TAB` 重排取前 32 位作 `mixin_key`；参数按 key 排序、过滤 `!'()*`、附 `wts`，`md5(query + mixin_key)` 得 `w_rid`。混密钥缓存 1 小时。

字幕 JSON 的 `body` 是原生时间轴，转格式只是排版，**没有任何识别误差**——这一点比任何语音转写都准。

---

## 故障排查

| 现象 | 原因 | 处置 |
|---|---|---|
| `subtitles: []` | 未登录，或该视频真没字幕 | 先 `--selftest`；登录态正常就是真没有 |
| `code=-101` | SESSDATA 过期 | 重新取 cookie |
| `HTTP Error 412` | 空间接口风控 | 工具已自动补 buvid3 + 重试 3 次；仍失败等 1-2 分钟 |
| 只拿到一页（50/57） | 翻页 `pn×ps` 偏移错乱 | 已修：固定 `ps=50` 翻页 + 去重 |
| `code=-404` | BV 号错 / 视频已删 | 核对链接 |
| 语言没匹配 | `-l` 别名不对 | `--list` 看实际 `lan`，然后 `-l ai-zh` 原样传 |

---

## 兜底：真的没字幕怎么办

只能音频转写。注意两个坑：

1. `playurl` 拿 dash 音频（`fnval=16` + wbi 签名，**无需登录**），下载 `.m4s` 必须带 `Referer: https://www.bilibili.com/`。
2. `faster-whisper` 依赖的 PyAV 19 上，`av.open(..., metadata_errors=)` 会 `TypeError`。绕过：自己用 `av.AudioResampler(format='fltp', layout='mono', rate=16000)` 解成 16k 单声道 numpy，再 `model.transcribe(array)`。2 核 CPU `small+int8` 约 1.1x 实时。

---

## 给 agent 用

仓库里的 [`AGENTS.md`](AGENTS.md) 是面向 agent 的操作契约：环境事实、命令契约、输出契约、失败模式对照表、以及明确不要做的事。接手环境的 agent 读那一份就够。

自检入口：

```bash
bili-sub --selftest     # 5 项：cookie / 登录态 / wbi / 字幕接口 / 网盘可写
```

---

## 免责

仅供个人学习与备份自己有权访问的内容使用。请遵守 B 站用户协议，控制请求频率，不要批量抓取后二次分发。
