# ui_assets.py
import customtkinter as ctk
from PIL import Image, ImageDraw
from config import BLUE, WHITE, TXT_G

def _logo_drawn(sz=64):
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = sz * 0.18
    d.rounded_rectangle([0, 0, sz, sz], radius=r, fill=BLUE)
    m = sz * 0.22
    d.rounded_rectangle([m, m, sz - m, sz - m], radius=r * 0.5, fill=WHITE)
    return im

def _logo(sz=36):
    img = _logo_drawn(sz * 2)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(sz, sz))

def nav_icon(kind, active=False, sz=20):
    im = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = BLUE if active else TXT_G
    
    if kind == "conn":
        d.rectangle([6, 12, 34, 28], outline=col, width=3)
        d.line([20, 28, 20, 34], fill=col, width=3)
        d.line([12, 34, 28, 34], fill=col, width=3)
    elif kind == "contacts":
        d.ellipse([14, 6, 26, 18], outline=col, width=3)
        d.arc([8, 20, 32, 36], start=180, end=360, fill=col, width=3)
    elif kind == "settings":
        d.ellipse([10, 10, 30, 30], outline=col, width=3)
        d.ellipse([17, 17, 23, 23], fill=col)
    
    return ctk.CTkImage(light_image=im, dark_image=im, size=(sz, sz))