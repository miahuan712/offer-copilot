# -*- coding: utf-8 -*-
"""小红书笔记抓取：链接解析 / 直连 HTML / Playwright 渲染 / CLI。

分层抓取（fetch_note）：
  1. 直连解析笔记页 HTML 中的 window.__INITIAL_STATE__（公开笔记无需登录）
  2. Playwright 无头渲染（可带登录 Cookie 抓需登录的笔记；未装 playwright 时自动跳过）
  3. 都失败返回 None，由调用方兜底（Jina Reader / 手动粘贴）

用法：
  python -m xhs <笔记链接> [--cookie 'a1=...; web_session=...'] [--proxy http://127.0.0.1:7897]
"""
import json
import re
import sys
import time
import threading
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item|search_result|showNotes|item|note)/([0-9a-zA-Z]+)")
_XSEC_TOKEN_RE = re.compile(r"xsec_token=([0-9a-f]+)")
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
    page_url = _build_page_url(parsed)
    try:
        html = fetch_html(page_url, cookie=cookie, proxy=proxy, timeout=15)
    except Exception:
        return None
    note = note_from_state(extract_initial_state(html))
    if note is None:
        return None
    note["reader"] = "direct"
    return note


# ---- Playwright 层（可选） ----

_lock = None
_browser = None
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


def _get_browser():
    global _browser, _pw
    if _browser is not None:
        return _browser
    from playwright.sync_api import sync_playwright
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    return _browser


def _reset_browser():
    global _browser, _pw
    try:
        if _browser is not None:
            _browser.close()
    except Exception:
        pass
    try:
        if _pw is not None:
            _pw.stop()
    except Exception:
        pass
    _browser = None
    _pw = None


def fetch_note_playwright(url, cookie="", proxy="", timeout=25):
    if not _playwright_available():
        return None
    with _get_lock():
        try:
            browser = _get_browser()
            ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
            if cookie:
                pairs = {}
                for part in cookie.split(";"):
                    if "=" in part:
                        k, v = part.strip().split("=", 1)
                        if v:
                            pairs[k.strip()] = v.strip()
                if pairs:
                    ctx.add_cookies([{"name": k, "value": v, "domain": ".xiaohongshu.com", "path": "/"}
                                     for k, v in pairs.items()])
            page = ctx.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("script", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            html = page.content()
            ctx.close()
            note = note_from_state(extract_initial_state(html))
            if note is None:
                return None
            note["reader"] = "playwright"
            return note
        except Exception:
            _reset_browser()
            return None


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

def fetch_note(url, cookie="", proxy=""):
    """返回 {title, desc, images, reader} 或 None。"""
    url = (url or "").strip()
    if not is_xhs_url(url):
        return None
    if ".xhslink.com" in url.lower():
        try:
            url = expand_short_url(url, cookie=cookie, proxy=proxy)
        except Exception:
            return None
    note = fetch_note_direct(url, cookie=cookie, proxy=proxy)
    if note:
        return note
    return fetch_note_playwright(url, cookie=cookie, proxy=proxy)


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
        print("用法: python -m xhs <笔记链接> [--cookie 'a1=...; web_session=...'] [--proxy http://127.0.0.1:7897]")
        return 2
    cookie, proxy = "", ""
    if "--cookie" in argv:
        i = argv.index("--cookie")
        cookie = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
    if "--proxy" in argv:
        i = argv.index("--proxy")
        proxy = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
    url = argv[0]
    parsed = parse_note_url(url)
    if parsed:
        cached = cache_get(parsed["note_id"])
        if cached:
            cached["_cache"] = True
            print(json.dumps(cached, ensure_ascii=False))
            return 0
    note = fetch_note(url, cookie=cookie, proxy=proxy)
    if note is None:
        print(json.dumps({"error": "抓取失败：无法解析该链接（可能需要登录 Cookie，或平台反爬拦截）"}, ensure_ascii=False))
        return 1
    if parsed:
        cache_set(parsed["note_id"], note)
    print(json.dumps(note, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())