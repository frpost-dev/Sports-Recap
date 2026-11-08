"""Render Instagram carousel slides (1080x1350, 4:5) with Pillow."""
import os
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
BG, PANEL = (14, 17, 23), (24, 29, 38)
FG, MUTED = (240, 242, 245), (130, 139, 152)
HERE = os.path.dirname(os.path.abspath(__file__))

FONTS = {
    "bold": [os.path.join(HERE, "fonts", "bold.ttf"),
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "C:/Windows/Fonts/arialbd.ttf"],
    "regular": [os.path.join(HERE, "fonts", "regular.ttf"),
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "C:/Windows/Fonts/arial.ttf"],
}


def font(kind, size):
    for p in FONTS[kind]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fit(draw, text, fnt, max_w):
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=fnt) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


@dataclass
class Row:
    top: str
    top_right: str = ""
    bottom: str = ""
    bottom_right: str = ""
    sub: str = ""
    top_win: bool = False
    bottom_win: bool = False


def _footer(d, brand, page, total):
    d.text((60, H - 70), brand, font=font("regular", 28), fill=MUTED)
    label = f"{page}/{total}"
    d.text((W - 60 - d.textlength(label, font=font("regular", 28)), H - 70), label,
           font=font("regular", 28), fill=MUTED)


def render_cover(path, brand, date_label, leagues, n_games, total_slides):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 18], fill=hex_rgb("#F5C518"))
    d.text((60, 330), "NIGHTLY", font=font("bold", 150), fill=FG)
    d.text((60, 490), "RECAP", font=font("bold", 150), fill=hex_rgb("#F5C518"))
    d.text((60, 700), fit(d, date_label, font("bold", 54), W - 120), font=font("bold", 54), fill=FG)
    d.text((60, 780), f"{n_games} results across {len(leagues)} leagues", font=font("regular", 36), fill=MUTED)
    y = 880
    line = ""
    for name in leagues:
        trial = (line + "  ·  " + name) if line else name
        if d.textlength(trial, font=font("regular", 32)) > W - 120:
            d.text((60, y), line, font=font("regular", 32), fill=MUTED)
            y += 50
            line = name
        else:
            line = trial
    if line:
        d.text((60, y), line, font=font("regular", 32), fill=MUTED)
    d.text((60, H - 140), "Swipe  →", font=font("bold", 40), fill=FG)
    _footer(d, brand, 1, total_slides)
    img.save(path)


def render_card(path, title, subtitle, rows, accent, brand, page, total_slides):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    acc = hex_rgb(accent)
    d.rectangle([0, 0, W, 18], fill=acc)
    d.rectangle([60, 80, 74, 190], fill=acc)
    d.text((96, 78), fit(d, title, font("bold", 70), W - 160), font=font("bold", 70), fill=FG)
    d.text((96, 158), subtitle, font=font("regular", 32), fill=MUTED)

    y, row_h, gap = 240, 148, 14
    f_b, f_r, f_s = font("bold", 42), font("regular", 42), font("regular", 27)
    for r in rows:
        d.rounded_rectangle([60, y, W - 60, y + row_h], radius=22, fill=PANEL)
        left_w = W - 120 - 160
        two_line = bool(r.bottom)
        ty = y + 14 if two_line else y + 24
        ft = f_b if r.top_win else f_r
        d.text((90, ty), fit(d, r.top, ft, left_w), font=ft, fill=FG if r.top_win else MUTED)
        if r.top_right:
            d.text((W - 90 - d.textlength(r.top_right, font=ft), ty), r.top_right, font=ft,
                   fill=FG if r.top_win else MUTED)
        if two_line:
            fb = f_b if r.bottom_win else f_r
            d.text((90, y + 62), fit(d, r.bottom, fb, left_w), font=fb, fill=FG if r.bottom_win else MUTED)
            if r.bottom_right:
                d.text((W - 90 - d.textlength(r.bottom_right, font=fb), y + 62), r.bottom_right, font=fb,
                       fill=FG if r.bottom_win else MUTED)
        if r.sub:
            sy = y + 112 if two_line else y + 84
            d.text((90, sy), fit(d, r.sub, f_s, W - 180), font=f_s, fill=acc)
        y += row_h + gap
    _footer(d, brand, page, total_slides)
    img.save(path)
