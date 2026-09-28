#!/usr/bin/env python3
"""Build the 'Diversifying AI Ownership' essay site.

Renders the Google Doc's first tab (Part I) as a long-form essay page. Later
tabs (Part II, appendices, notes) stay in Google Docs; Part II is linked at
the end. The companion page summarises Bostrom's OGI paper (drafted with AI
assistance, labelled as such) and links the PDF instead of reproducing it.

Stdlib only for the build; Pillow (optional) for images and social cards.
"""
import base64
import hashlib
import os
import re
import shutil
import sys
import html as htmllib
import urllib.request
from datetime import datetime, timezone

from docrender import parse_tabs, plain, to_article

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
CACHE = os.path.join(ROOT, "data", "cache")
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
UA = {"User-Agent": "Mozilla/5.0 (compatible; ai-ownership-builder)"}

DOC_ID = "1ISGuSmNMRT_nLYeUUxHtPGdQVdfn3h0TyNW-GYnGgvU"
BASE_URL = os.environ.get("SITE_BASE",
                          "https://haukehillebrandt.github.io/ai-ownership").rstrip("/")
SITE_TITLE = "Diversifying AI Ownership"
AUTHOR = "Hauke Hillebrandt"
DOC_URL = f"https://docs.google.com/document/d/{DOC_ID}/edit"
OGI_PDF = "https://nickbostrom.com/ogimodel.pdf"
HOME_URL = "https://haukehillebrandt.github.io/hfh.pw/"


def fetch(url, timeout=60, retries=2):
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def _visible_text(html_str):
    html_str = re.sub(r"<(?:style|head)[^>]*>.*?</(?:style|head)>", " ", html_str, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_str))


def cached_doc_html(tab):
    """First-tab export, with a committed fallback cache.

    Google's export markup is volatile (class names shuffle) even when the
    doc is unchanged; the cache is only rewritten on real edits so the
    Action's auto-commit doesn't churn.
    """
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "doc.html")
    try:
        body = fetch(f"https://docs.google.com/document/d/{DOC_ID}/export?format=html&tab={tab}")
        if "<body" not in body:
            raise ValueError("no body in export")
        if os.path.exists(path):
            old = open(path).read()
            if _visible_text(old) == _visible_text(body):
                return old
        with open(path, "w") as f:
            f.write(body)
        return body
    except Exception as e:  # noqa: BLE001
        if os.path.exists(path):
            print(f"[warn] doc fetch failed ({e}); using cache", file=sys.stderr)
            return open(path).read()
        raise


def template(name):
    return open(os.path.join(ROOT, "templates", name)).read()


def render(tpl, **kw):
    for k, v in kw.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    return tpl


def esc(s):
    return htmllib.escape(s, quote=True)


# ---------------------------------------------------------------- images

def optimize_image_bytes(data, ext):
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if getattr(im, "is_animated", False):
            return data, ext
        buf = io.BytesIO()
        w, h = im.size
        if w > 1400:
            im = im.resize((1400, max(1, round(h * 1400 / w))), Image.LANCZOS)
        if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] >= 250:
            im = im.convert("RGB")
        if im.mode in ("RGBA", "LA", "P"):
            im.save(buf, "PNG", optimize=True)
            out_ext = "png"
        else:
            im.convert("RGB").save(buf, "WEBP", quality=82)
            out_ext = "webp"
        out = buf.getvalue()
        if len(out) < len(data):
            return out, out_ext
    except Exception:  # noqa: BLE001
        pass
    return data, ext


DATA_URI_RE = re.compile(
    r'src="data:image/(png|jpe?g|gif|webp|svg\+xml);base64,([A-Za-z0-9+/=]+)"')


def externalize_images(html_str):
    img_dir = os.path.join(DIST, "img")
    os.makedirs(img_dir, exist_ok=True)

    def repl(m):
        ext = {"jpeg": "jpg", "svg+xml": "svg"}.get(m.group(1), m.group(1))
        try:
            data = base64.b64decode(m.group(2))
        except Exception:  # noqa: BLE001
            return m.group(0)
        stem = hashlib.sha1(data).hexdigest()[:16]
        if ext != "svg":
            data, ext = optimize_image_bytes(data, ext)
        name = f"{stem}.{ext}"
        path = os.path.join(img_dir, name)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(data)
        return f'src="img/{name}"'

    return DATA_URI_RE.sub(repl, html_str)


# ---------------------------------------------------------------- social cards

def make_og(title, subtitle, out_name):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    import textwrap

    def font(size, weight=700):
        path = os.path.join(FONT_DIR, f"Inter-{weight}.ttf")
        return ImageFont.truetype(path, size) if os.path.exists(path) else None

    if not font(10):
        return
    im = Image.new("RGB", (1200, 630), "#0f1115")
    d = ImageDraw.Draw(im)
    d.rectangle([80, 84, 108, 112], fill="#1f3fe0")
    d.text((126, 80), AUTHOR, font=font(30, 500), fill="#9aa3b2")
    y = 210
    for line in textwrap.wrap(title, width=24)[:3]:
        d.text((80, y), line, font=font(76), fill="#ffffff")
        y += 90
    d.text((80, y + 24), subtitle, font=font(32, 500), fill="#9aa3b2")
    im.save(os.path.join(DIST, out_name), "PNG", optimize=True)


# ---------------------------------------------------------------- build

def build():
    print("Fetching doc…")
    first, tabs = "t.0", []
    try:
        first, tabs = parse_tabs(fetch(f"https://docs.google.com/document/d/{DOC_ID}/preview"))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] tab lookup failed ({e}); using the first tab", file=sys.stderr)
    export = cached_doc_html(first)

    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    for f in os.listdir(os.path.join(ROOT, "static")):
        shutil.copy(os.path.join(ROOT, "static", f), DIST)

    print("Rendering…")
    art = to_article(export, [SITE_TITLE] + [t for i, t, _ in tabs if i == first], author=AUTHOR)
    body = art["body"]
    start = re.search(r'<h[1-3] id="abstract">', body)
    if start:  # the hero replaces the doc's own title block
        body = body[start.start():]
    body = externalize_images(body)

    part2 = next(((i, t) for i, t, _ in tabs if t.lower().startswith("part ii")), None)
    part2_link = ""
    if part2:
        href = f"{DOC_URL}?tab={part2[0]}"
        block = render(template("_continue.html"), HREF=esc(href), TITLE=esc(part2[1]))
        notes = body.find('<section class="footnotes">')
        body = body[:notes] + block + body[notes:] if notes != -1 else body + block
        part2_link = (f'<a href="{esc(href)}" target="_blank" rel="noopener">'
                      f'{esc(part2[1].split(":")[0])} (working draft) ↗</a>')

    toc = [(int(m.group(1)), m.group(2), plain(m.group(3)))
           for m in re.finditer(r'<h([12]) id="([^"]+)">(.*?)</h\1>', body, re.S)]
    toc_html = "\n".join(
        f'<a class="toc-{lvl}" href="#{tid}">{esc(text[:64] + ("…" if len(text) > 64 else ""))}</a>'
        for lvl, tid, text in toc)

    updated = datetime.now(timezone.utc).strftime("%-d %B %Y")
    common = dict(BASE=BASE_URL, DOC_URL=DOC_URL, OGI_PDF=OGI_PDF, HOME_URL=HOME_URL, UPDATED=updated)
    open(os.path.join(DIST, "index.html"), "w").write(render(
        template("index.html"), CONTENT=body, TOC=toc_html, PART2_LINK=part2_link, **common))
    open(os.path.join(DIST, "ogi.html"), "w").write(render(template("ogi.html"), **common))

    make_og(SITE_TITLE, "Working paper · Part I", "og.png")
    make_og("The Open Global Investment model", "A companion note on Bostrom (2025)", "og-ogi.png")

    open(os.path.join(DIST, "robots.txt"), "w").write(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")
    open(os.path.join(DIST, "sitemap.xml"), "w").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{BASE_URL}/</loc></url>\n"
        f"  <url><loc>{BASE_URL}/ogi</loc></url>\n</urlset>\n")
    open(os.path.join(DIST, "404.html"), "w").write(
        f'<!doctype html><meta http-equiv="refresh" content="0;url={BASE_URL}/">')

    # sanity gate: refuse to ship an obviously broken build
    text_len = len(plain(body))
    if text_len < 8_000 or len(toc) < 3:
        print(f"BUILD REJECTED: text={text_len} toc={len(toc)}", file=sys.stderr)
        sys.exit(1)
    print(f"Done: {text_len / 1000:.0f}k chars from tab {first!r}, {len(toc)} TOC entries, "
          f"Part II link: {bool(part2)} -> dist/")


if __name__ == "__main__":
    build()
