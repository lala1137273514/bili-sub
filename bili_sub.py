#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bili-sub — 从 B 站拉取 CC / AI 字幕（srt / txt / json）

用法示例:
  bili_sub.py BV1MsnG6TEf3 --list                 # 只列出字幕轨
  bili_sub.py BV1MsnG6TEf3                        # 拉中文（默认 ai-zh）
  bili_sub.py BV1MsnG6TEf3 --all                  # 拉全部语言
  bili_sub.py 'https://www.bilibili.com/video/BV1xxx?p=2' -l zh,en
  bili_sub.py BV1xxx -o ./out --fmt srt,txt,json
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
API = "https://api.bilibili.com"
REFERER = "https://www.bilibili.com/"

# wbi 混密钥重排表（B 站前端固定表）
MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

LANG_ALIAS = {
    "zh": ("ai-zh", "zh-CN", "zh-Hans"),
    "cn": ("ai-zh", "zh-CN", "zh-Hans"),
    "中文": ("ai-zh", "zh-CN", "zh-Hans"),
    "en": ("ai-en", "en-US"),
    "ja": ("ai-ja", "ja-JP"),
    "jp": ("ai-ja", "ja-JP"),
}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def die(msg, code=2):
    log("错误: " + msg)
    sys.exit(code)


class Bili:
    def __init__(self, cookie="", verbose=False):
        self.cookie = (cookie or "").strip()
        self.verbose = verbose
        self._mk = None
        self._mk_ts = 0.0

    # ---------- 底层请求 ----------
    def _headers(self, referer=REFERER):
        h = {"User-Agent": UA, "Referer": referer, "Accept": "application/json,text/plain,*/*"}
        if self.cookie:
            h["Cookie"] = self.cookie
        return h

    def raw(self, url, referer=REFERER):
        req = urllib.request.Request(url, headers=self._headers(referer))
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=25) as r:
                    return r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code in (412, 429, 503) and attempt < 3:
                    time.sleep(3.0 * (attempt + 1))
                    if attempt == 0:
                        try:
                            self.ensure_buvid()
                        except Exception:
                            pass
                    continue
                raise
        raise RuntimeError("请求失败: " + url)

    def api(self, path, params=None):
        q = urllib.parse.urlencode(params or {})
        url = API + path + (("?" + q) if q else "")
        if self.verbose:
            log("GET " + url)
        d = json.loads(self.raw(url))
        if d.get("code") != 0:
            raise RuntimeError("%s -> code=%s msg=%s" % (path, d.get("code"), d.get("message")))
        return d["data"]

    # ---------- wbi 签名 ----------
    def mixin_key(self, force=False):
        if self._mk and not force and time.time() - self._mk_ts < 3600:
            return self._mk
        nav = self.api("/x/web-interface/nav")
        w = nav["wbi_img"]
        raw = (w["img_url"].rsplit("/", 1)[-1].split(".")[0]
               + w["sub_url"].rsplit("/", 1)[-1].split(".")[0])
        self._mk = "".join(raw[i] for i in MIXIN_TAB)[:32]
        self._mk_ts = time.time()
        return self._mk

    def wbi_params(self, params):
        mk = self.mixin_key()
        p = dict(params)
        p["wts"] = int(time.time())
        clean = {k: "".join(c for c in str(v) if c not in "!'()*")
                 for k, v in sorted(p.items())}
        q = urllib.parse.urlencode(clean)
        p["w_rid"] = hashlib.md5((q + mk).encode("utf-8")).hexdigest()
        return p

    # ---------- 业务 ----------
    def login_info(self):
        try:
            d = self.api("/x/web-interface/nav")
            return bool(d.get("isLogin")), d.get("uname") or ""
        except Exception as e:
            log("nav 检查失败: %s" % e)
            return False, ""

    def view_by_bvid(self, bvid):
        return self.api("/x/web-interface/view", {"bvid": bvid})

    def view_by_aid(self, aid):
        return self.api("/x/web-interface/view", {"aid": aid})

    def pages(self, data):
        ps = data.get("pages") or []
        if not ps:
            ps = [{"cid": data["cid"], "page": 1, "part": data.get("title", ""), "duration": data.get("duration")}]
        return ps

    def subtitle_tracks(self, aid, cid, bvid=None):
        p = {"aid": aid, "cid": cid}
        if bvid:
            p["bvid"] = bvid
        d = self.api("/x/player/wbi/v2", self.wbi_params(p))
        return ((d.get("subtitle") or {}).get("subtitles") or [])

    def ensure_buvid(self):
        """补 buvid3/buvid4，显著降低空间接口 412 概率"""
        if "buvid3=" in (self.cookie or ""):
            return
        try:
            d = self.api("/x/frontend/finger/spi")
            parts = []
            if d.get("b_3"):
                parts.append("buvid3=" + d["b_3"])
            if d.get("b_4"):
                parts.append("buvid4=" + d["b_4"])
            if parts:
                self.cookie = ((self.cookie + "; ") if self.cookie else "") + "; ".join(parts)
        except Exception:
            pass

    def space_videos(self, mid, limit=5, order="pubdate", page_size=50):
        """UP 主空间视频列表（固定页宽翻页 + 去重，需登录 cookie + wbi 签名）"""
        self.ensure_buvid()
        out, seen, pn, total = [], set(), 1, None
        while len(out) < limit and pn <= 40:
            p = self.wbi_params({"mid": int(mid), "ps": page_size, "pn": pn, "order": order,
                                 "platform": "web", "web_location": 1550101})
            d = self.api("/x/space/wbi/arc/search", p)
            total = (d.get("page") or {}).get("count", total)
            vl = (d.get("list") or {}).get("vlist") or []
            if not vl:
                break
            for v in vl:
                bv = v.get("bvid")
                if bv and bv not in seen:
                    seen.add(bv)
                    out.append(v)
            if len(vl) < page_size:
                break
            pn += 1
            time.sleep(1.2)
        log("空间接口声明总数: %s，实际可取: %d" % (total, len(out)))
        return out[:limit]

    def subtitle_body(self, url):
        if url.startswith("//"):
            url = "https:" + url
        return (json.loads(self.raw(url, referer="https://www.bilibili.com/")) or {}).get("body") or []


def parse_target(s):
    """BV 号 / av 号 / 完整 URL / b23.tv 短链 -> (key_dict, page_no)"""
    s = s.strip()
    page = 1
    if "b23.tv" in s:
        try:
            req = urllib.request.Request(s, headers={"User-Agent": UA})
            final = urllib.request.urlopen(req, timeout=20).geturl()
            s = final
            log("短链解析 -> %s" % final)
        except Exception as e:
            die("短链解析失败: %s" % e)
    m = re.search(r"[?&]p=(\d+)", s)
    if m:
        page = max(1, int(m.group(1)))
    m = re.search(r"BV[0-9A-Za-z]{10}", s)
    if m:
        return {"bvid": m.group(0)}, page
    m = re.search(r"av(\d+)", s, re.I)
    if m:
        return {"aid": int(m.group(1))}, page
    if re.fullmatch(r"\d+", s):
        return {"aid": int(s)}, page
    die("无法识别的目标: %r（支持 BV 号 / av 号 / 视频 URL）" % s)


def safe_name(s, maxlen=80):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", s or "").strip(" .")
    return (s or "untitled")[:maxlen]


def chinese_base(path):
    b = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"_(ai-[a-z]+|[a-z]{2}-[A-Za-z]+)$", "", b)


def fmtdur(sec):
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return ""
    if sec <= 0:
        return ""
    h, m, ss = sec // 3600, sec % 3600 // 60, sec % 60
    return ("%d:%02d:%02d" % (h, m, ss)) if h else ("%d:%02d" % (m, ss))


def ts(x):
    h = int(x // 3600)
    m = int(x % 3600 // 60)
    sec = x % 60
    return ("%02d:%02d:%06.3f" % (h, m, sec)).replace(".", ",")


FORMATS = ("srt", "txt", "para", "json", "vtt", "ass", "lrc", "csv", "jsonl", "md")
EXT = {"para": "para.txt"}


def to_srt(body):
    out = []
    for i, line in enumerate(body, 1):
        out.append("%d\n%s --> %s\n%s\n\n" % (i, ts(line["from"]), ts(line["to"]), line["content"]))
    return "".join(out)


def _t(x, sep="."):
    h = int(x // 3600)
    m = int(x % 3600 // 60)
    sec = x % 60
    return ("%02d:%02d:%06.3f" % (h, m, sec)).replace(".", sep)


def render(body, fmt):
    """把字幕 body 渲染成指定格式"""
    if fmt == "para":
        # 把碎句合并成自然段：句末标点 + 长度阈值 / 长停顿 才断段，最适合喂模型
        paras, cur, prev_end = [], [], None
        for x in body:
            txt = (x.get("content") or "").strip()
            if not txt:
                continue
            gap = (x["from"] - prev_end) if prev_end is not None else 0.0
            cur.append(txt)
            prev_end = x["to"]
            joined = "".join(cur)
            punct = bool(re.search(r"[。！？!?…；;]$", txt))
            if (punct and len(joined) >= 50) or len(joined) >= 160 or gap >= 2.5:
                paras.append("".join(cur))
                cur = []
        if cur:
            paras.append("".join(cur))
        return "\n\n".join(paras) + "\n"
    if fmt == "srt":
        return to_srt(body)
    if fmt == "txt":
        return "\n".join(x["content"] for x in body) + "\n"
    if fmt == "json":
        return json.dumps(body, ensure_ascii=False, indent=1)
    if fmt == "jsonl":
        return "".join(json.dumps({"from": x["from"], "to": x["to"], "content": x["content"]},
                                  ensure_ascii=False) + "\n" for x in body)
    if fmt == "vtt":
        out = ["WEBVTT", ""]
        for i, x in enumerate(body, 1):
            out.append(str(i))
            out.append("%s --> %s" % (_t(x["from"]), _t(x["to"])))
            out.append(x["content"])
            out.append("")
        return "\n".join(out)
    if fmt == "ass":
        head = ("[Script Info]\nTitle: bili-sub\nScriptType: v4.00+\n"
                "PlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
                "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                "Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
                "0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n\n[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        def at(x):
            h = int(x // 3600); m = int(x % 3600 // 60); sec = x % 60
            return "%d:%02d:%05.2f" % (h, m, sec)
        return head + "".join("Dialogue: 0,%s,%s,Default,,0,0,0,,%s\n" %
                              (at(x["from"]), at(x["to"]), x["content"].replace("\n", " ")) for x in body)
    if fmt == "lrc":
        return "".join("[%02d:%05.2f]%s\n" % (int(x["from"] // 60), x["from"] % 60, x["content"]) for x in body)
    if fmt == "csv":
        def q(v):
            v = str(v).replace('"', '""')
            return '"%s"' % v
        return "from,to,content\n" + "".join("%s,%s,%s\n" % (x["from"], x["to"], q(x["content"])) for x in body)
    if fmt == "md":
        return "".join("- **[%02d:%05.2f]** %s\n" % (int(x["from"] // 60), x["from"] % 60, x["content"])
                       for x in body)
    raise ValueError("未知格式: " + fmt)


def pick_tracks(tracks, langs):
    """按语言过滤；langs 为空表示全要"""
    if not langs:
        return tracks
    want = []
    for l in langs:
        l = l.strip()
        if not l:
            continue
        want.extend(LANG_ALIAS.get(l.lower(), (l,)))
    picked, seen = [], set()
    for t in tracks:
        hay = " ".join(str(t.get(k, "")) for k in ("lan", "lan_doc", "id_str")).lower()
        if any(w.lower() in hay for w in want) and t["lan"] not in seen:
            seen.add(t["lan"])
            picked.append(t)
    return picked


def load_cookie(args):
    def norm(v):
        v = (v or "").strip()
        if not v:
            return ""
        return v if "=" in v else "SESSDATA=" + v

    if args.cookie is not None:
        return norm(args.cookie)
    if args.cookie_file:
        if not os.path.isfile(args.cookie_file):
            die("cookie 文件不存在: " + args.cookie_file)
        with open(args.cookie_file, encoding="utf-8") as f:
            return norm(f.read())
    for p in [os.path.expanduser("~/.config/bili-sub/cookie"),
              os.path.expanduser("~/.bili_sub_cookie")]:
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    c = norm(f.read())
                if c:
                    return c
            except OSError:
                pass
    return norm(os.environ.get("BILI_COOKIE") or os.environ.get("BILI_SESSDATA", ""))


def run_one(cli, target, args, langs, fmts):
    """处理单个目标，返回 {"count","files","videos","owner"}"""
    key, page_no = parse_target(target)
    data = cli.view_by_bvid(key["bvid"]) if "bvid" in key else cli.view_by_aid(key["aid"])
    owner = (data.get("owner") or {}).get("name") or ""
    title = data.get("title", "")
    bvid = data.get("bvid", "")
    aid = data.get("aid")
    pages = cli.pages(data)
    log("视频: %s (bvid=%s aid=%s, %d P)" % (title, bvid, aid, len(pages)))
    npages = len(pages)
    pages = [p for p in pages if int(p.get("page", 1)) == page_no] or pages[:1]

    outdir = args.outdir
    if not args.list:
        os.makedirs(outdir, exist_ok=True)

    files, videos = [], []
    for p in pages:
        cid = p["cid"]
        pno = int(p.get("page", 1))
        part = p.get("part") or title
        tracks = cli.subtitle_tracks(aid, cid, bvid)
        head = "[P%d] %s" % (pno, title if len(pages) == 1 else part)
        if not tracks:
            log(head + " -> 无字幕轨（UP 未上传 CC / 未生成 AI 字幕）")
            continue
        log(head + " -> %d 条字幕轨: %s" % (
            len(tracks), ", ".join("%s(%s)" % (t.get("lan"), t.get("lan_doc")) for t in tracks)))
        if args.list:
            for t in tracks:
                print(json.dumps({k: t.get(k) for k in
                                  ("lan", "lan_doc", "ai_status", "type", "subtitle_url")},
                                 ensure_ascii=False))
            continue
        picked = pick_tracks(tracks, langs)
        if not picked:
            log("  没有匹配语言 %s，可用: %s" % (langs, [t.get("lan") for t in tracks]))
            continue
        for t in picked:
            try:
                body = cli.subtitle_body(t["subtitle_url"])
            except Exception as e:
                log("  下载失败 %s: %s" % (t.get("lan"), e))
                continue
            if not body:
                log("  %s 内容为空，跳过" % t.get("lan"))
                continue
            if npages == 1:
                stem = "%s_(%s)_%s" % (title, bvid, t.get("lan"))
            else:
                stem = "%s_(%s)_P%d_%s" % (part, bvid, pno, t.get("lan"))
            base = safe_name(stem)
            made = []
            for fm in FORMATS:
                if fm not in fmts:
                    continue
                path = os.path.join(outdir, base + "." + EXT.get(fm, fm))
                with open(path, "w", encoding="utf-8") as f:
                    f.write(render(body, fm))
                log("  ✓ %s  %s  %s" % (t.get("lan"), fm, path))
                files.append(path)
                made.append(path)
            if t.get("lan") == "ai-zh" or pno > 1:
                vchars = len(re.sub(r"\s", "", "".join(x["content"] for x in body)))
                videos.append({"bvid": bvid, "aid": aid, "cid": cid, "title": title if pno == 1 else part,
                               "page": pno, "length": fmtdur(p.get("duration")),
                               "chars": vchars, "files": [os.path.basename(x) for x in made]})
    return {"count": len(files), "files": files, "videos": videos, "owner": owner}


def write_merged(outdir, videos):
    """生成 _manifest.json 与 _合集_全部字幕.txt"""
    import datetime
    out = []
    man = []
    blocks = []
    for i, v in enumerate(videos, 1):
        txt = ""
        for fn in v.get("files") or []:
            if fn.endswith(".txt"):
                fp = os.path.join(outdir, fn)
                if os.path.isfile(fp):
                    txt = open(fp, encoding="utf-8").read().strip()
                    break
        man.append({"idx": i, "bvid": v.get("bvid"), "aid": v.get("aid"), "title": v.get("title"),
                    "length": v.get("length"), "chars": v.get("chars"), "files": v.get("files")})
        blocks.append("=" * 70 + "\n【%d】%s\nBV: %s  时长: %s  字数: %s\n%s\n\n%s\n"
                      % (i, v.get("title"), v.get("bvid"), v.get("length"), v.get("chars"), "=" * 70, txt))
    mp = os.path.join(outdir, "_manifest.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    out.append(mp)
    cp = os.path.join(outdir, "_合集_全部字幕.txt")
    with open(cp, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))
    out.append(cp)
    log("已生成 %s 与 %s" % (os.path.basename(mp), os.path.basename(cp)))
    return out


def sync_drive(files, owner, root):
    d = os.path.join(root, safe_name(owner or "unknown"))
    os.makedirs(d, exist_ok=True)
    for f in files:
        try:
            shutil.copy2(f, os.path.join(d, safe_name(os.path.basename(f))))
        except Exception as e:
            log("同步失败 %s: %s" % (os.path.basename(f), e))
    return d


def selftest(cli):
    """环境自检：cookie / 登录态 / wbi 签名 / 字幕接口 / 网盘可达性"""
    results = []

    def chk(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, str(e)[:120]
        results.append((name, ok, detail))
        log("%s %s  %s" % ("PASS" if ok else "FAIL", name, detail))
        return ok

    chk("cookie 已配置", lambda: (bool(cli.cookie), "%d 字符" % len(cli.cookie)))
    chk("登录态有效", lambda: (lambda lg: (lg[0], "uname=" + (lg[1] or "-")))(cli.login_info()))
    chk("wbi 混密钥", lambda: (bool(cli.mixin_key()), cli.mixin_key()[:12] + "..."))
    def _sub_check():
        v = cli.view_by_bvid("BV135xT6TEFz")
        tr = cli.subtitle_tracks(v["aid"], v["cid"], v["bvid"])
        return len(tr) > 0, "%d 条字幕轨（探针视频）" % len(tr)
    chk("字幕接口可达", _sub_check)
    chk("网盘挂载可写", lambda: (os.access("/mnt/gdrive", os.W_OK), "/mnt/gdrive"))
    npass = sum(1 for _, ok, _ in results if ok)
    log("自检结果: %d/%d 通过" % (npass, len(results)))
    return npass == len(results)


def main():
    ap = argparse.ArgumentParser(description="下载 B 站 CC / AI 字幕")
    ap.add_argument("target", nargs="?", help="BV 号 / av 号 / 视频 URL；- 表示从 stdin 读列表")
    ap.add_argument("-l", "--lang", default="zh", help="语言，逗号分隔；all 表示全部（默认 zh）")
    ap.add_argument("--all", action="store_true", help="下载全部语言")
    ap.add_argument("--list", action="store_true", help="只列出字幕轨，不下载")
    ap.add_argument("-o", "--outdir", default="subs_out", help="输出目录")
    ap.add_argument("--fmt", default="srt,txt",
                    help="输出格式：srt,txt,para,json,jsonl,vtt,ass,lrc,csv,md（默认 srt,txt；para=分段纯文本，最适合喂模型）")
    ap.add_argument("--cookie", help="SESSDATA 或完整 Cookie 串")
    ap.add_argument("--cookie-file", help="cookie 文件路径")
    ap.add_argument("-f", "--from-file", help="批量：每行一个 BV 号/URL 的文件，- 表示 stdin")
    ap.add_argument("--up", help="UP 主 UID 或空间链接，取其视频列表")
    ap.add_argument("--limit", type=int, default=5, help="配合 --up：取最近 N 个视频（默认 5）")
    ap.add_argument("--order", default="pubdate", help="配合 --up：排序 pubdate/click/stow")
    ap.add_argument("--drive", nargs="?", const="/mnt/gdrive/B站", default=None,
                    help="同步到网盘根目录（默认 /mnt/gdrive/B站），按 UP 主名建子目录")
    ap.add_argument("--merge", action="store_true", help="单个视频也生成 _manifest/_合集")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="环境自检（cookie/登录/wbi/接口/网盘）")
    args = ap.parse_args()

    cookie = load_cookie(args)
    cli = Bili(cookie, args.verbose)
    if args.selftest:
        sys.exit(0 if selftest(cli) else 1)
    logged, uname = cli.login_info()
    if cookie:
        log("登录态: %s%s" % ("有效 " if logged else "无效/已过期", ("(" + uname + ")") if uname else ""))
    else:
        log("未提供 cookie —— B 站不会下发字幕轨，请用 --cookie / --cookie-file / BILI_SESSDATA")
    if not logged:
        log("继续尝试（部分视频的公开字幕轨道可能仍可见）")

    targets = []
    up = args.up
    if not up and args.target:
        m = re.search(r"space\.bilibili\.com/(\d+)", args.target)
        if m:
            up = m.group(1)
    if up:
        m = re.search(r"(\d{3,})", str(up))
        if not m:
            die("无法从 --up 里解析出 UID: %r" % up)
        mid = m.group(1)
        vs = cli.space_videos(mid, args.limit, args.order)
        log("UP主 %s -> 取到 %d 个视频（%s 排序）" % (mid, len(vs), args.order))
        for v in vs:
            log("  %s  %s  %s" % (v.get("bvid"), (v.get("title") or "")[:40], v.get("length", "")))
        targets = [v["bvid"] for v in vs]
    elif args.from_file:
        if args.from_file == "-":
            targets = [x.strip() for x in sys.stdin if x.strip() and not x.startswith("#")]
        else:
            with open(args.from_file, encoding="utf-8") as f:
                targets = [x.strip() for x in f if x.strip() and not x.strip().startswith("#")]
    elif args.target and args.target != "-":
        targets = [args.target]
    elif not sys.stdin.isatty():
        targets = [x.strip() for x in sys.stdin if x.strip() and not x.startswith("#")]
    if not targets:
        die("请给出 BV 号 / URL，或用 -f 文件 / 管道批量传入")

    langs = None if (args.all or args.lang.strip().lower() == "all") else [x for x in args.lang.split(",") if x.strip()]
    fmts = {x.strip().lower() for x in args.fmt.split(",") if x.strip()}
    bad = fmts - set(FORMATS)
    if bad:
        die("不支持的格式: %s（可选: %s）" % (",".join(sorted(bad)), ",".join(FORMATS)))

    total, all_files, all_videos, owners = 0, [], [], []
    for i, t in enumerate(targets, 1):
        if len(targets) > 1:
            log("---------- [%d/%d] %s ----------" % (i, len(targets), t))
        try:
            res = run_one(cli, t, args, langs, fmts)
            total += res["count"]
            all_files += res["files"]
            all_videos += res["videos"]
            if res.get("owner") and res["owner"] not in owners:
                owners.append(res["owner"])
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log("失败 %s: %s" % (t, e))
            if len(targets) == 1:
                sys.exit(1)
    if args.list:
        return
    extras = write_merged(args.outdir, all_videos) if (len(all_videos) > 1 or args.merge) else []
    all_files += extras
    log("完成，共写出 %d 个字幕文件到 %s" % (total, args.outdir))
    if args.drive and all_files:
        owner = owners[0] if owners else "unknown"
        d = sync_drive(all_files, owner, args.drive)
        log("已同步到网盘: %s （%d 个文件）" % (d, len(all_files)))
    if total == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
