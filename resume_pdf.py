# -*- coding: utf-8 -*-
import os
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

_FONT = "STSong-Light"

_PAGE_W, _PAGE_H = A4
_MARGIN = 44
_TOP = _PAGE_H - _MARGIN
_BOTTOM = _MARGIN
_LINE_H = 13
_LINE_H_EN = 12
_SIZE_SMALL = 8.5
_SIZE_NORMAL = 9.5
_SIZE_HEAD = 11.5
_SIZE_NAME = 19
_SIZE_NAME_EN = 18


def _init_font():
    global _FONT
    candidates = [
        (r"C:\Windows\Fonts\msyh.ttc", "MSYH"),
        (r"C:\Windows\Fonts\simhei.ttf", "SimHei"),
        (r"C:\Windows\Fonts\simsun.ttc", "SimSun"),
        (r"/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
    ]
    for path, name in candidates:
        if os.path.exists(path):
            try:
                from reportlab.pdfbase.ttfonts import TTFont

                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
                _FONT = name
                return
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    _FONT = "STSong-Light"


_init_font()


def _wrap(text, font_name, size, max_width):
    """按可用宽度折行。含中文按字符折行，纯英文按单词折行。"""
    s = str(text or "").strip()
    if not s:
        return []
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in s)
    if has_cjk:
        lines, cur = [], ""
        for ch in s:
            if pdfmetrics.stringWidth(cur + ch, font_name, size) <= max_width:
                cur += ch
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        return lines
    words = s.split(" ")
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip() if cur else w
        if pdfmetrics.stringWidth(t, font_name, size) <= max_width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_pdf(data, lang="zh", photo=None):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Resume")
    y = _TOP
    blue = (0.13, 0.36, 0.62)

    if lang == "en":
        F = {"normal": "Helvetica", "bold": "Helvetica-Bold"}
        name_size = _SIZE_NAME_EN
        line_h = _LINE_H_EN
        small = _SIZE_SMALL - 0.5
        normal = _SIZE_NORMAL - 0.5
        head = _SIZE_HEAD - 0.5
    else:
        F = {"normal": _FONT, "bold": _FONT}
        name_size = _SIZE_NAME
        line_h = _LINE_H
        small = _SIZE_SMALL
        normal = _SIZE_NORMAL
        head = _SIZE_HEAD

    max_w = _PAGE_W - _MARGIN * 2
    col_w = max_w / 3.0
    gap_body = 13
    gap_head = 12

    def draw(x, yy, s, size, color=None, bold=False):
        c.setFont(F["bold"] if bold else F["normal"], size)
        if color:
            c.setFillColorRGB(*color)
        else:
            c.setFillColorRGB(0, 0, 0)
        c.drawString(x, yy, s)

    def draw_right(x, yy, s, size, bold=False):
        c.setFont(F["bold"] if bold else F["normal"], size)
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(x, yy, s)

    def fits(h):
        return y - h >= _BOTTOM

    # ---- 证件照（右上角，独占顶部右侧区域，正文避让） ----
    has_photo = bool(photo) and os.path.exists(str(photo))
    photo_w, photo_h = 58, 74
    header_w = (max_w - photo_w - 12) if has_photo else max_w
    if has_photo:
        try:
            px = _PAGE_W - _MARGIN - photo_w
            c.drawImage(str(photo), px, _TOP - photo_h, photo_w, photo_h,
                        preserveAspectRatio=True, anchor="c", mask="auto")
        except Exception:
            has_photo = False

    def draw_block(x, s, size, gap, bold=False, color=None, indent=0, width=None):
        """自动折行绘制，返回新的 y 坐标；空间不足时截断剩余行。"""
        nonlocal y
        lines = _wrap(s, F["bold"] if bold else F["normal"], size, (width or max_w) - indent)
        for ln in lines:
            if ln and not fits(gap):
                break
            if ln:
                draw(x + indent, y, ln, size, color, bold)
            y -= gap
        return y

    def draw_rich_bullet(x, text, size, gap, max_width):
        """要点：小标题（冒号前）加粗 + 正文，自动折行。"""
        nonlocal y
        full = "• " + str(text)
        label = ""
        colon = str(text).find("：")
        if colon < 0:
            colon = str(text).find(":")
        if 0 < colon <= 14:
            label = "• " + str(text)[:colon + 1]
        lines = _wrap(full, F["normal"], size, max_width)
        for i, ln in enumerate(lines):
            if not ln:
                y -= gap
                continue
            if i == 0 and label and ln.startswith(label):
                c.setFont(F["bold"], size)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(x, y, label)
                rest = ln[len(label):]
                if rest:
                    c.setFont(F["normal"], size)
                    c.drawString(x + pdfmetrics.stringWidth(label, F["bold"], size), y, rest)
            else:
                c.setFont(F["normal"], size)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(x, y, ln)
            y -= gap

    def draw_head(item):
        """条目头：公司/岗位/时间 各占一行 1/3（时间右对齐）。"""
        nonlocal y
        company = str(item.get("company", "") or "").strip()
        role = str(item.get("role", "") or "").strip()
        tm = str(item.get("time", "") or "").strip()
        if company or role or tm:
            lc = _wrap(company, F["bold"], normal, col_w)
            lr = _wrap(role, F["bold"], normal, col_w)
            lt = _wrap(tm, F["bold"], normal, col_w)
            n = max(len(lc), len(lr), len(lt))
            for i in range(n):
                if not fits(gap_head):
                    break
                if i < len(lc) and lc[i].strip():
                    draw(_MARGIN, y, lc[i], normal, bold=True)
                if i < len(lr) and lr[i].strip():
                    draw(_MARGIN + col_w, y, lr[i], normal, bold=True)
                if i < len(lt) and lt[i].strip():
                    draw_right(_PAGE_W - _MARGIN, y, lt[i], normal, bold=True)
                y -= gap_head
        else:
            head_txt = str(item.get("head", "") or "").strip()
            if head_txt:
                if not fits(gap_head):
                    return
                draw_block(_MARGIN, head_txt, normal, gap_head, bold=True)

    def section(title):
        nonlocal y
        if not fits(22):
            return False
        y -= 12
        c.setFont(F["bold"], head)
        c.setFillColorRGB(*blue)
        c.drawString(_MARGIN, y, title)
        c.setStrokeColorRGB(*blue)
        c.setLineWidth(1)
        c.line(_MARGIN, y - 3, _PAGE_W - _MARGIN, y - 3)
        c.setFillColorRGB(0, 0, 0)
        y -= 14
        return True

    draw_block(_MARGIN, str(data.get("name", "") or ""), name_size, name_size + 4, bold=True, width=header_w)
    y -= 4
    if data.get("target"):
        draw_block(_MARGIN, str(data["target"]), normal, gap_body, bold=True, width=header_w)
        y -= 1
    if data.get("contact"):
        draw_block(_MARGIN, str(data["contact"]), small, 11, width=header_w)
        y -= 7
    if has_photo:
        y = min(y, _TOP - photo_h - 4)

    if data.get("education"):
        if section("Education" if lang == "en" else "教育背景"):
            draw_block(_MARGIN, str(data["education"]), normal, gap_body)
            y -= 2
    if data.get("skills"):
        if section("Skills" if lang == "en" else "技能"):
            draw_block(_MARGIN, str(data["skills"]), normal, gap_body)
            y -= 2

    for sec in data.get("sections", []) or []:
        items = sec.get("items") or []
        if not items:
            continue
        if not section(str(sec.get("title", "") or "经历")):
            break
        for item in items:
            draw_head(item)
            for b in item.get("bullets", []) or []:
                if not fits(line_h):
                    break
                draw_rich_bullet(_MARGIN + 12, str(b), small, line_h, max_w - 12)
            y -= 2

    c.showPage()
    c.save()
    return buf.getvalue()