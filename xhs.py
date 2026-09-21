# -*- coding: utf-8 -*-
"""小红书笔记抓取：链接解析 / 直连 HTML / Playwright 渲染 / CLI。

分层抓取（fetch_note）：
  1. 直连解析笔记页 HTML 中的 window.__INITIAL_STATE__（公开笔记无需登录）
  2. Playwright 无头渲染（可带登录 Cookie 抓需登录的笔记；未装 playwright 时自动跳过）
  3. 都失败返回 None，由调用方兜底（Jina Reader / 手动粘贴）

用法：
  python -m xhs --login                                        # 手动登录，保存登录态
  python -m xhs <笔记链接> [--cookie 'a1=...; web_session=...'] # 抓取
  # 环境变量：XHS_PROXY=http://127.0.0.1:7897  代理；XHS_HEADLESS=0 使用有头浏览器
"""
import json
import os
import random
import re
import sys
import time
import threading
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 登录态持久化目录：手动登录后 Cookie/本地存储保存在这里，后续抓取自动复用
PROFILE_DIR = Path(__file__).parent / "xhs_profile"

PLAYWRIGHT_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--window-size=1440,900",
]

# 抹除 headless / 自动化痕迹
STEALTH_JS = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
const _q = window.navigator.permissions && window.navigator.permissions.query;
if (_q) {
    window.navigator.permissions.query = (p) =>
        p && p.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _q(p);
}
"""

_NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item|search_result|showNotes|item|note)/([0-9a-zA-Z]+)")
_XSEC_TOKEN_RE = re.compile(r"xsec_token=([0-9a-zA-Z_\-]+)")
_XSEC_SOURCE_RE = re.compile(r"xsec_source=([0-9a-zA-Z_]+)")


def is_xhs_url(url):
    url = (url or "").strip().lower()
    return any(h in url for h in ("xiaohongshu.com", "xhslink.com", "rednote.com"))


def parse_note_url(url):
    url = (url or "").strip()
    m = _NOTE_ID_RE.search(url)
    if not m:
        return None
    tok = _XSEC_TOKEN_RE.search(url)
    src = _XSEC_SOURCE_RE.search(url)
    return {
        "note_id": m.group(1),
        "xsec_token": tok.group(1) if tok else "",
        "xsec_source": src.group(1) if src else "pc_search",
    }


def expand_short_url(url, cookie="", proxy="", timeout=15):
    import requests
    headers = {"User-Agent": UA}
    if cookie:
        headers["Cookie"] = cookie
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=headers, timeout=timeout, proxies=proxies, allow_redirects=True)
    return r.url


def _build_page_url(parsed, base="https://www.xiaohongshu.com"):
    u = "%s/explore/%s" % (base, parsed["note_id"])
    if parsed["xsec_token"]:
        u += "?xsec_token=%s&xsec_source=%s" % (parsed["xsec_token"], parsed["xsec_source"] or "pc_search")
    return u


def fetch_html(url, cookie="", proxy="", timeout=15):
    import requests
    headers = {
        "User-Agent": UA,
        "Referer": "https://www.xiaohongshu.com/",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if cookie:
        headers["Cookie"] = cookie
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.text


def extract_initial_state(html):
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _find_note(state):
    try:
        dmap = state["note"]["noteDetailMap"]
        if isinstance(dmap, dict):
            for v in dmap.values():
                n = ((v or {}).get("note") or {}) if isinstance(v, dict) else {}
                if n:
                    return n
    except Exception:
        pass
    try:
        return state["note"]["noteDetailMap"]
    except Exception:
        return None
    return None


def note_from_state(state):
    if not state:
        return None
    note = _find_note(state)
    if not note:
        return None
    title = str(note.get("title") or "").strip()
    desc = str(note.get("desc") or "").strip()
    images = []
    for im in (note.get("imageList") or []):
        u = im.get("urlDefault") or im.get("url") or ""
        if u:
            images.append(u)
    return {"title": title, "desc": desc, "images": images}


def fetch_note_direct(url, cookie="", proxy=""):
    parsed = parse_note_url(url)
    if not parsed:
        return None
    # 直接用原始链接（保留 xsec_token/source/xhsshare 等参数），避免重建丢参数
    page_url = url
    try:
        html = fetch_html(page_url, cookie=cookie, proxy=proxy, timeout=15)
    except Exception:
        return None
    note = note_from_state(extract_initial_state(html))
    if note is None:
        return None
    note["reader"] = "direct"
    return note


# ---- Playwright 层（登录态持久化 + 反检测 + 随机延迟） ----

_lock = None
_context = None
_pw = None


def _playwright_available():
    try:
        import playwright  # noqa
        return True
    except Exception:
        return False


def _get_lock():
    global _lock
    if _lock is None:
        _lock = threading.Lock()
    return _lock


def _env_proxy():
    return os.environ.get("XHS_PROXY", "").strip()


def _headless_mode():
    # XHS_HEADLESS=0 时使用有头浏览器（更不易被检测）；默认无头
    return os.environ.get("XHS_HEADLESS", "1").strip() != "0"


def _get_context():
    global _context, _pw
    if _context is not None:
        return _context
    from playwright.sync_api import sync_playwright
    _pw = sync_playwright().start()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": _headless_mode(),
        "args": PLAYWRIGHT_ARGS,
        "user_agent": UA,
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "viewport": {"width": 1440, "height": 900},
        "screen": {"width": 1440, "height": 900},
        "ignore_https_errors": True,
    }
    p = _env_proxy()
    if p:
        launch_kwargs["proxy"] = {"server": p}
    _context = _pw.chromium.launch_persistent_context(**launch_kwargs)
    _context.add_init_script(STEALTH_JS)
    return _context


def _reset_browser():
    global _context, _pw
    try:
        if _context is not None:
            _context.close()
    except Exception:
        pass
    try:
        if _pw is not None:
            _pw.stop()
    except Exception:
        pass
    _context = None
    _pw = None


def _inject_cookies(ctx, cookie):
    if not cookie:
        return
    pairs = {}
    for part in cookie.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            if v:
                pairs[k.strip()] = v.strip()
    if not pairs:
        return
    try:
        ctx.add_cookies([{"name": k, "value": v, "domain": ".xiaohongshu.com", "path": "/"}
                         for k, v in pairs.items()])
    except Exception:
        pass


def _human_pause(page):
    try:
        page.mouse.move(random.randint(200, 1200), random.randint(200, 700))
        time.sleep(random.uniform(0.4, 1.4))
        page.mouse.move(random.randint(300, 1400), random.randint(300, 800))
        time.sleep(random.uniform(0.2, 0.8))
    except Exception:
        time.sleep(random.uniform(0.5, 1.5))


def _risk_control_detected(page):
    try:
        title = page.title() or ""
        if any(k in title for k in ("验证", "verify", "security", "captcha", "访问过于频繁", "登录")):
            return True
        if "verify" in page.url.lower() or "captcha" in page.url.lower():
            return True
    except Exception:
        pass
    return False


def fetch_note_playwright(url, cookie="", proxy="", timeout=25, max_retries=2):
    """带登录态持久化与反检测的浏览器抓取。返回 {title, desc, images, reader} 或 None。"""
    if not _playwright_available():
        return None
    if proxy and not _env_proxy():
        print("  [提示] Playwright 代理请用环境变量 XHS_PROXY=http://127.0.0.1:7897 配置", file=sys.stderr)
    with _get_lock():
        for attempt in range(max_retries + 1):
            try:
                ctx = _get_context()
                _inject_cookies(ctx, cookie)
                page = ctx.new_page()
                page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                _human_pause(page)
                try:
                    page.wait_for_selector("script", timeout=8000)
                except Exception:
                    pass
                for _ in range(random.randint(1, 3)):
                    page.mouse.wheel(0, random.randint(200, 900))
                    time.sleep(random.uniform(0.3, 1.0))
                html = page.content()
                risky = _risk_control_detected(page)
                page.close()
                note = note_from_state(extract_initial_state(html))
                if note is not None:
                    note["reader"] = "playwright"
                    return note
                if risky:
                    print("  [风控] 命中验证/登录页，等待 %ds 后重试..." % random.randint(15, 30), file=sys.stderr)
                    time.sleep(random.uniform(15, 30))
                    continue
                return None
            except Exception as e:
                print("  [错误] Playwright 抓取失败: %s" % e, file=sys.stderr)
                _reset_browser()
                time.sleep(random.uniform(8, 20))
        return None


def _find_search_notes(state):
    """从搜索页 __INITIAL_STATE__ 提取带有效 xsec_token 的笔记列表。"""
    try:
        sn = state["searchInfo"]["searchNotes"]
    except Exception:
        sn = None
    if not isinstance(sn, list):
        return []
    out = []
    for item in sn:
        if not isinstance(item, dict):
            continue
        nid = item.get("id") or item.get("noteId") or ""
        tok = item.get("xsecToken") or item.get("xsec_token") or ""
        src = item.get("xsecSource") or "pc_search"
        title = str(item.get("displayTitle") or item.get("title") or "").strip()
        if nid and tok:
            out.append({"note_id": nid, "xsec_token": tok, "xsec_source": src, "title": title})
    return out


def search_notes(keyword, cookie="", proxy="", timeout=25):
    """用登录态（持久化 profile）搜索，返回带有效 xsec_token 的笔记列表。

    分享链接里的 xsec_token 绑定原会话/IP，换环境即失效；
    而搜索页会为当前登录会话下发新的 token，可用于后续抓取。
    """
    if not _playwright_available():
        return []
    import urllib.parse
    url = "https://www.xiaohongshu.com/search_result?keyword=%s&source=web_search_result_notes" % urllib.parse.quote(keyword)
    with _get_lock():
        try:
            ctx = _get_context()
            _inject_cookies(ctx, cookie)
            page = ctx.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            _human_pause(page)
            try:
                page.wait_for_selector("script", timeout=8000)
            except Exception:
                pass
            for _ in range(random.randint(1, 2)):
                page.mouse.wheel(0, random.randint(300, 900))
                time.sleep(random.uniform(0.3, 0.9))
            html = page.content()
            page.close()
            return _find_search_notes(extract_initial_state(html))
        except Exception:
            _reset_browser()
            return []


def fetch_note_via_search(keyword, note_id="", cookie="", proxy=""):
    """搜索拿到新 token 后抓取笔记。note_id 为空时取第一条。"""
    for note in search_notes(keyword, cookie=cookie, proxy=proxy):
        if note_id and note["note_id"] != note_id:
            continue
        u = "https://www.xiaohongshu.com/explore/%s?xsec_token=%s&xsec_source=%s" % (
            note["note_id"], note["xsec_token"], note["xsec_source"] or "pc_search")
        got = fetch_note_playwright(u, cookie=cookie, proxy=proxy)
        if got:
            got["reader"] = "search"
            return got
    return None


def login_interactive():
    """打开浏览器窗口手动登录小红书，登录态将持久化保存到 xhs_profile 目录。"""
    from playwright.sync_api import sync_playwright
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "args": PLAYWRIGHT_ARGS,
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "viewport": {"width": 1440, "height": 900},
        "ignore_https_errors": True,
    }
    p = _env_proxy()
    if p:
        launch_kwargs["proxy"] = {"server": p}
    ctx = pw.chromium.launch_persistent_context(**launch_kwargs)
    ctx.add_init_script(STEALTH_JS)
    page = ctx.new_page()
    page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded")
    print("请在打开的浏览器中完成登录（扫码/手机号验证码）。")
    input("登录成功后回到这里按回车保存会话...")
    ctx.close()
    pw.stop()
    print("登录态已保存到 %s" % PROFILE_DIR)


# ---- 下载图片（供视觉模型转写） ----

def download_image(url, cookie="", proxy="", timeout=20):
    import requests
    headers = {"User-Agent": UA, "Referer": "https://www.xiaohongshu.com/"}
    if cookie:
        headers["Cookie"] = cookie
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.content


# ---- 顶层编排 ----

def fetch_note(url, cookie="", proxy="", keyword=""):
    """返回 {title, desc, images, reader} 或 None。"""
    url = (url or "").strip()
    if not is_xhs_url(url):
        return None
    if ".xhslink.com" in url.lower():
        try:
            url = expand_short_url(url, cookie=cookie, proxy=proxy)
        except Exception:
            return None
    # 优先 Playwright（登录态 + 反检测），避免裸 requests 触发 TLS 指纹风控
    if _playwright_available():
        note = fetch_note_playwright(url, cookie=cookie, proxy=proxy)
        if note:
            return note
    time.sleep(random.uniform(2, 5))
    note = fetch_note_direct(url, cookie=cookie, proxy=proxy)
    if note:
        return note
    # 分享 token 失效（页面不见了/风控）时，用登录态搜索换取新 token 重试
    if keyword:
        parsed = parse_note_url(url)
        nid = parsed["note_id"] if parsed else ""
        note = fetch_note_via_search(keyword, note_id=nid, cookie=cookie, proxy=proxy)
        if note:
            return note
    return None


# ---- 本地缓存 ----

def cache_path(note_id):
    return Path(__file__).parent / "xhs_cache" / ("%s.json" % note_id)


def cache_get(note_id, max_age=86400):
    p = cache_path(note_id)
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > max_age:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_set(note_id, data):
    try:
        p = cache_path(note_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---- CLI ----

def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("用法: python -m xhs <笔记链接> [--cookie 'a1=...; web_session=...'] [--proxy http://127.0.0.1:7897] [--search '关键词']")
        print("      python -m xhs --login   # 手动登录并保存登录态")
        print("      python -m xhs <链接> --search '关键词'  # 分享token失效时，用登录态搜索换新token再抓取")
        return 2
    if argv[0] == "--login":
        if not _playwright_available():
            print("需要先安装 playwright: pip install playwright && playwright install chromium", file=sys.stderr)
            return 1
        login_interactive()
        return 0
    cookie, proxy, keyword = "", "", ""
    if "--cookie" in argv:
        i = argv.index("--cookie")
        cookie = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
    if "--proxy" in argv:
        i = argv.index("--proxy")
        proxy = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
    if "--search" in argv:
        i = argv.index("--search")
        keyword = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
    url = argv[0]
    parsed = parse_note_url(url)
    if parsed:
        cached = cache_get(parsed["note_id"])
        if cached:
            cached["_cache"] = True
            print(json.dumps(cached, ensure_ascii=False))
            return 0
    note = fetch_note(url, cookie=cookie, proxy=proxy, keyword=keyword)
    if note is None:
        print(json.dumps({"error": "抓取失败：无法解析该链接（可能需要登录 Cookie，或平台反爬拦截）"}, ensure_ascii=False))
        return 1
    if parsed:
        cache_set(parsed["note_id"], note)
    print(json.dumps(note, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())