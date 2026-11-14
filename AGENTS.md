# AGENTS.md — bili-sub 工作流契约

给任何接手这份环境的 agent 看。读完这一页就能干活，不需要再猜。

> 第 2 节是**本机部署快照**（绝对路径、挂载点、cookie 位置）。换机器只改那一节，其余命令与契约通用。

---

## 1. 这是什么

一条命令把 B 站的 **CC 字幕 / AI 字幕**（含 `ai-zh` `ai-en` `ai-ja` 等 8 轨）拉成本地文件，并能按 UP 主自动归档到 Google Drive。

**不走录屏、不走 vCaptions、不走 whisper 转写。** 唯一门槛是一条有效的 `SESSDATA`。

```
bili-sub <BV号/URL>          → srt + txt
bili-sub --up <UID> --drive  → 该 UP 全部视频，落到网盘 <UP昵称>/ 目录
```

---

## 2. 环境事实（别重新探测，直接用）

| 项 | 值 |
|---|---|
| 工具入口 | `/usr/local/bin/bili-sub`（wrapper → `bili_sub.py`） |
| cookie 提取器 | `/usr/local/bin/bili-cookie`（→ `bili_cookie_from_chrome.py`） |
| cookie 文件 | `~/.config/bili-sub/cookie`，权限 600，内容形如 `SESSDATA=...` |
| 网盘挂载 | `/mnt/gdrive`（rclone mount，`--vfs-cache-mode writes --vfs-write-back 5s`） |
| 网盘归档根 | `/mnt/gdrive/B站/`（`--drive` 默认值） |
| Python | 3.13，主工具**零第三方依赖**；`bili-cookie` 需要 `websocket-client` |
| Chromium 调试口 | `127.0.0.1:9222`（`--user-data-dir=~/chrome-profile`） |

---

## 3. 前置检查（每次动手前跑一次，2 秒）

```bash
bili-sub --selftest
```

预期 `5/5 通过`，逐项含义：

| 检查项 | FAIL 时怎么办 |
|---|---|
| cookie 已配置 | `bili-cookie` 或手工写 `~/.config/bili-sub/cookie` |
| 登录态有效 | SESSDATA 过期，重新取 |
| wbi 混密钥 | 网络问题，重试 |
| 字幕接口可达 | 探针视频改版 / 风控，见第 6 节 |
| 网盘挂载可写 | `pgrep -af rclone`，挂载掉了要重启 |

退出码：`0` 全通过，`1` 有失败项。

---

## 4. 命令契约

```bash
# 单视频，默认中文 srt+txt → ./subs_out
bili-sub BV1MsnG6TEf3

# 只看有几轨字幕，不下载
bili-sub BV1MsnG6TEf3 --list

# 指定语言 / 全部语言 / 指定格式
bili-sub BV1MsnG6TEf3 -l en,ja
bili-sub BV1MsnG6TEf3 --all
bili-sub BV1MsnG6TEf3 --fmt txt          # 喂模型只要 txt
bili-sub BV1MsnG6TEf3 --fmt srt          # 只要播放器用的
bili-sub BV1MsnG6TEf3 --fmt srt,txt,json,vtt,ass,lrc,csv,jsonl,md,para

# 分P / 完整 URL / 短链
bili-sub 'https://www.bilibili.com/video/BV1xxx/?p=2'
bili-sub 'https://b23.tv/xxxxx'

# 批量：文件每行一个，或 stdin
bili-sub -f list.txt -o out
cat list.txt | bili-sub -

# UP 主空间
bili-sub --up 324213598 --limit 5
bili-sub 'https://space.bilibili.com/324213598' --limit 100
bili-sub --up 324213598 --limit 100 --order click     # 按播放量

# 同步网盘（按 owner.name 自动建目录 + 生成 manifest/合集）
bili-sub --up 324213598 --limit 100 --drive
bili-sub --up 324213598 --limit 100 --all --drive --fmt srt,txt
```

退出码：`0` 成功；`1` 无字幕 / 全部失败 / 鉴权失败；`2` 参数或 cookie 文件错误。

---

## 5. 输出契约（下游脚本按这个解析）

**本地命名**
```
<标题>_(BV号)_<语言>.srt / .txt        单P
<分P名>_(BV号)_P2_<语言>.srt           多P
```
- `(BVxxxxxxxxxx)` 是唯一锚点，标题可改不影响检索
- 语言后缀：`ai-zh` `ai-en` `ai-ja` `ai-es` `ai-ar` `ai-pt` `ai-th` `ai-id`
- 标题会被 `safe_name` 清洗（非法字符→`_`，截断 80 字符）

**网盘结构**（`--drive`）
```
<drive 根>/
  _说明.md
  <UP昵称>/
    _manifest.json            [{idx,bvid,aid,title,length,chars,files[]}, ...]
    _合集_全部字幕.txt         所有视频 txt 拼接，带 ===== 分隔头
    <标题>_(BV号)_ai-zh.srt
    <标题>_(BV号)_ai-zh.txt
```

**_manifest.json 字段**：`idx bvid aid title page length chars files[]`，`chars` 是去空白后的中文字数。

---

## 6. 失败模式 → 处置（照着做，别自由发挥）

| 现象 | 真实原因 | 处置 |
|---|---|---|
| `subtitle.subtitles: []` | 未登录，或该视频真的没字幕 | 先 `bili-sub --selftest`；登录态 OK 就是真没字幕 |
| `code=-101 账号未登录` | SESSDATA 过期 | 重新取 cookie |
| `HTTP Error 412` | 空间/播放接口风控 | 工具已自动补 buvid3 + 重试 3 次（3/6/9s）；仍失败就等 1-2 分钟再跑 |
| 只拿到一页（如 50 个而不是 57） | **翻页 offset 错乱**：`pn×ps` 决定偏移，改 `ps` 会重叠 | 已修：固定 `page_size=50` 翻页 + bvid 去重。别自己改 `ps` |
| 云端看不到刚写的文件 | `--vfs-write-back 5s`，异步上传 | **等 10-30 秒**再 `rclone lsf`；`to upload 0` 才是真完成 |
| 文件名被改成 `_(P1_)` 之类 | 用 `sed -E 's/\(\.\.\.\)/.../'` 处理中文名 | ERE 里 `\(` 是**字面括号**不是分组。一律用 Python `re` |
| `File name too long` | 中文标题 × 3 字节逼近 255 | `safe_name` 已截 80 字符；超长标题自己再截 |
| 写入云端后 md5 不符 | 缓存未回写读完 | 等 `to upload 0` 再校验 |

---

## 7. 明确不要做的事

1. **不要默认上 whisper。** B 站有 AI 字幕，接口空只说明没登录态，不是没字幕。转写是最后兜底（36 分钟音频在 2 核上要 33 分钟，且 `faster_whisper` 在 PyAV 19 上会 `TypeError: metadata_errors`，要用 `av.AudioResampler` 自己解成 16k 单声道 numpy）。
2. **不要为了「看起来成功」编执行结果。** 所有验证必须真跑，云端必须 `rclone lsf` 实列。
3. **不要动 `MIXIN_TAB`。** 那是 B 站前端固定重排表，改了签名全废。
4. **不要把 SESSDATA 写进代码或提交。** 只在 `~/.config/bili-sub/cookie`（600）。
5. **不要给网盘文件重命名。** 名字里的 `(BV号)` 是唯一锚点。
6. **不要并发轰炸 space 接口。** 翻页间隔已设 1.2s，去掉必 412。

---

## 8. 一次性安装（幂等，可反复跑）

```bash
bash setup.sh
```

做的事：装 wrapper 到 `/usr/local/bin` → 检查/提示 cookie → 装 `websocket-client`（缺才装）→ 跑 `--selftest`。

---

## 9. 已验证的样本（回归基准）

| 对象 | 结果 |
|---|---|
| `BV1MsnG6TEf3` | 8 轨，中文 1036 条，`00:00:00,080 → 00:36:28,400` |
| UID `324213598` | 5 视频 / 12 文件（10 字幕 + manifest + 合集）/ 37062 字 / md5 全一致 |
| UID `1892407222` | 57 视频 / 116 文件（114 字幕 + 2 汇总）/ 50062 字 / md5 全一致 / 0 无字幕 |

---

## 10. 格式选择速查

喂模型默认用 `txt`（1.00x 体积，无时间戳噪音）。需要引用具体时间点用 `md`（2.47x）。`srt`（4.01x）只给播放器和剪辑。`json`（9.98x）只在写程序时用。`para`（0.92x，分段纯文本）是给模型的最优解，但当前约定统一用 `txt`。
