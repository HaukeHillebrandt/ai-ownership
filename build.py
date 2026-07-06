#!/usr/bin/env python3
"""Build the 'Diversifying AI Ownership' essay site.

Fetches the Google Doc at build time, converts its exported HTML into clean
semantic HTML (situational-awareness.ai-style typography), and renders a
static site into dist/. The companion page summarises Bostrom's OGI paper
and links to the PDF (no full reproduction).

Stdlib only for the build; Pillow (optional) for images/social cards.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import html as htmllib
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
CACHE = os.path.join(ROOT, "data", "cache")
UA = {"User-Agent": "Mozilla/5.0 (compatible; ai-ownership-builder)"}

DOC_ID = "1ISGuSmNMRT_nLYeUUxHtPGdQVdfn3h0TyNW-GYnGgvU"
BASE_URL = os.environ.get("SITE_BASE",
                          "https://haukehillebrandt.github.io/ai-ownership").rstrip("/")
SITE_TITLE = "Diversifying AI Ownership"
DOC_URL = f"https://docs.google.com/document/d/{DOC_ID}/edit"
OGI_PDF = "https://nickbostrom.com/ogimodel.pdf"


def fetch(url, timeout=60, retries=2):
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def cached_doc_html():
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "doc.html")
    try:
        body = fetch(f"https://docs.google.com/document/d/{DOC_ID}/export?format=html")
        if "<body" not in body:
            raise ValueError("no body in export")
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


# ---------------------------------------------------------------- doc -> clean html

def parse_class_styles(export_html):
    """Map Google's generated CSS classes to inline semantics."""
    styles = {}
    m = re.search(r"<style[^>]*>(.*?)</style>", export_html, re.S)
    if not m:
        return styles
    for rule in re.finditer(r"([^{}]+)\{([^}]*)\}", m.group(1)):
        selectors, body = rule.group(1), rule.group(2)
        props = {
            "bold": "font-weight:700" in body or "font-weight:bold" in body,
            "italic": "font-style:italic" in body,
            "underline": "text-decoration:underline" in body,
            "sup": "vertical-align:super" in body,
        }
        if not any(props.values()):
            continue
        for sel in selectors.split(","):
            sel = sel.strip()
            if sel.startswith("."):
                styles[sel[1:]] = props
    return styles


def unwrap_google_link(url):
    m = re.match(r"https://www\.google\.com/url\?q=([^&]+)", url)
    if m:
        return urllib.parse.unquote(m.group(1))
    return url


def transform_doc(export_html):
    """Google Docs export HTML -> clean semantic HTML."""
    styles = parse_class_styles(export_html)
    body = re.search(r"<body[^>]*>(.*)</body>", export_html, re.S).group(1)

    def classes_of(tag_attrs):
        m = re.search(r'class="([^"]*)"', tag_attrs)
        return m.group(1).split() if m else []

    def span_semantics(attrs):
        bold = italic = sup = False
        for c in classes_of(attrs):
            p = styles.get(c)
            if p:
                bold |= p["bold"]
                italic |= p["italic"]
                sup |= p["sup"]
        return bold, italic, sup

    out = body
    # 1. unwrap redirect links, drop trailing google params
    out = re.sub(r'href="(https://www\.google\.com/url\?q=[^"]+)"',
                 lambda m: 'href="' + esc(unwrap_google_link(htmllib.unescape(m.group(1)))) + '"',
                 out)
    # 2. spans -> strong/em/sup or plain text
    def span_repl(m):
        attrs, inner = m.group(1), m.group(2)
        bold, italic, sup = span_semantics(attrs)
        if sup:
            return f"<sup>{inner}</sup>"
        if bold and italic:
            return f"<strong><em>{inner}</em></strong>"
        if bold:
            return f"<strong>{inner}</strong>"
        if italic:
            return f"<em>{inner}</em>"
        return inner
    prev = None
    while prev != out:  # spans can nest
        prev = out
        out = re.sub(r"<span([^>]*)>((?:(?!</?span).)*)</span>", span_repl, out, flags=re.S)

    # 3. strip class/style/id junk from structural tags (keep footnote ids/hrefs)
    def clean_tag(m):
        tag = m.group(1)
        attrs = m.group(2)
        keep = ""
        for attr in ("id", "href", "src", "alt", "colspan", "rowspan"):
            am = re.search(rf'{attr}="([^"]*)"', attrs)
            if am:
                keep += f' {attr}="{am.group(1)}"'
        return f"<{tag}{keep}>"
    out = re.sub(r"<(h[1-6]|p|ul|ol|li|a|td|tr|table|img|div)\b([^>]*)>", clean_tag, out)

    # 4. drop empty paragraphs
    out = re.sub(r"<p[^>]*>(?:\s|&nbsp;|<br>)*</p>", "", out)
    # heading ids for TOC anchors (replace Google's h.xxx ids with slugs);
    # drop Google's audio-tab artifact headings entirely
    used_ids = set()

    def heading_id(m):
        level, inner = m.group(1), m.group(3)
        text = htmllib.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if text.lower() in ("listen to this tab", ""):
            return ""
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "s"
        base = slug
        i = 2
        while slug in used_ids:
            slug = f"{base}-{i}"
            i += 1
        used_ids.add(slug)
        return f'<h{level} id="{slug}">{inner}</h{level}>'
    out = re.sub(r"<h([1-4])([^>]*)>(.*?)</h\1>", heading_id, out, flags=re.S)

    # 5. drop the doc's own title/byline preamble (hero replaces it)
    m = re.search(r'<h1 id="abstract">', out)
    if m:
        out = out[m.start():]

    # 6. images: lazy-load
    out = out.replace("<img ", '<img loading="lazy" decoding="async" ')
    return out


def extract_toc(clean_html):
    toc = []
    for m in re.finditer(r'<h([12]) id="([^"]+)">(.*?)</h\1>', clean_html, re.S):
        text = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
        if text:
            toc.append({"level": int(m.group(1)), "id": m.group(2), "title": text})
    return toc


# ---------------------------------------------------------------- og image

def make_og(title, subtitle, out_name):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    import textwrap
    font_path = None
    for f in ["/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
              "/System/Library/Fonts/Supplemental/Georgia.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]:
        if os.path.exists(f):
            font_path = f
            break
    if not font_path:
        return
    im = Image.new("RGB", (1200, 630), "#14212e")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1200, 10], fill="#d4a24e")
    big = ImageFont.truetype(font_path, 72)
    small = ImageFont.truetype(font_path, 32)
    y = 200
    for line in textwrap.wrap(title, width=26)[:3]:
        d.text((80, y), line, font=big, fill="#f5f1e8")
        y += 92
    d.text((84, y + 30), subtitle, font=small, fill="#a8b4c0")
    im.save(os.path.join(DIST, out_name), "PNG", optimize=True)


# ---------------------------------------------------------------- build

def build():
    print("Fetching doc…")
    export = cached_doc_html()

    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    for f in os.listdir(os.path.join(ROOT, "static")):
        shutil.copy(os.path.join(ROOT, "static", f), DIST)

    print("Transforming…")
    clean = transform_doc(export)
    clean = externalize_images(clean)

    toc = extract_toc(clean)
    toc_html = "\n".join(
        f'<a class="toc-{t["level"]}" href="#{t["id"]}">'
        f'{esc(t["title"][:64] + ("…" if len(t["title"]) > 64 else ""))}</a>'
        for t in toc)

    updated = datetime.now(timezone.utc).strftime("%d %B %Y")
    index = render(template("index.html"),
                   BASE=BASE_URL,
                   CONTENT=clean,
                   TOC=toc_html,
                   DOC_URL=DOC_URL,
                   OGI_PDF=OGI_PDF,
                   UPDATED=updated)
    open(os.path.join(DIST, "index.html"), "w").write(index)

    ogi = render(template("ogi.html"),
                 BASE=BASE_URL, OGI_PDF=OGI_PDF, DOC_URL=DOC_URL, UPDATED=updated)
    open(os.path.join(DIST, "ogi.html"), "w").write(ogi)

    make_og(SITE_TITLE, "Hauke Hillebrandt (2025) · Working paper", "og.png")
    make_og("Open Global Investment", "A companion note on Bostrom (2025)", "og-ogi.png")

    open(os.path.join(DIST, "robots.txt"), "w").write(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")
    open(os.path.join(DIST, "sitemap.xml"), "w").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{BASE_URL}/</loc></url>\n"
        f"  <url><loc>{BASE_URL}/ogi</loc></url>\n</urlset>\n")
    open(os.path.join(DIST, "404.html"), "w").write(
        f'<!doctype html><meta http-equiv="refresh" content="0;url={BASE_URL}/">')

    # sanity gate
    text_len = len(re.sub(r"<[^>]+>", "", clean))
    if text_len < 30_000 or len(toc) < 4:
        print(f"BUILD REJECTED: text={text_len} toc={len(toc)}", file=sys.stderr)
        sys.exit(1)
    print(f"Done: {text_len/1000:.0f}k chars, {len(toc)} TOC entries -> dist/")


if __name__ == "__main__":
    build()
