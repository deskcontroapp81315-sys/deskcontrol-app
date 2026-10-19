# activation_tab.py - تبويب Activation (قسم لحاله) لبرنامج DeskControl Pro
#
# الاستخدام من main.py:
#     from activation_tab import build_activation_tab
#     build_activation_tab(self.content, self.cfg)
#
# هاد الملف مستقل: ما بيستورد من main.py (عشان ما يصير import دائري)،
# وبيستخدم نفس cfg يلي بالبرنامج الأساسي، فأي تغيير بالكود بينحفظ مباشرة.

import time
from datetime import datetime

import customtkinter as ctk

from config import F, save_config
import license_ext as LX

# ───────── الألوان (نفس باليت البرنامج) ─────────
CARD     = "#FFFFFF"
CARD2    = "#EEF6FC"
BORDER   = "#E2EDF7"
ACCENT   = "#1A9BE6"
ACCENT_H = "#1589CC"
GREEN    = "#17B26A"
GREEN_BG = "#EAFAF2"
BLUE_BG  = "#E8F4FD"
RED      = "#E0556A"
RED_BG   = "#FDEEF0"
ORANGE   = "#E08A1E"
TXT      = "#10243E"
MUTED    = "#44566B"
MUTED2   = "#7C90A6"


def _label(parent, text, size=12, bold=False, color=MUTED, **kw):
    return ctk.CTkLabel(parent, text=text, font=F(size, bold), text_color=color, **kw)


def _expiry_info(key):
    """يرجع (نص, لون) لتاريخ انتهاء الاشتراك حسب الكود."""
    exp = LX.expires_at(key)
    if exp is None:
        return "Lifetime license  ·  never expires", GREEN
    left = exp - time.time()
    date = datetime.fromtimestamp(exp).strftime("%Y-%m-%d  %H:%M")
    days = int(left // 86400)
    if days >= 1:
        remain = f"{days} day{'s' if days != 1 else ''} left"
        color = GREEN if days > 7 else ORANGE
    else:
        hours = max(1, int(left // 3600))
        remain = f"{hours} hour{'s' if hours != 1 else ''} left"
        color = RED
    return f"Expires on {date}  ·  {remain}", color


class ActivationTab:
    """يبني صفحة Activation كاملة داخل `parent` (الإطار الرئيسي للمحتوى)."""

    def __init__(self, parent, cfg):
        self.parent = parent
        self.cfg = cfg          # نفس القاموس الأساسي للبرنامج (بيتعدّل مباشرة)
        self._build()

    # ───────── الواجهة ─────────
    def _build(self):
        _label(self.parent, "Activation", 22, True, TXT).pack(anchor="w")
        _label(self.parent, "Enter your license key to activate DeskControl Pro.",
               12, False, MUTED).pack(anchor="w", pady=(2, 16))

        card = ctk.CTkFrame(self.parent, corner_radius=16, fg_color=CARD,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, 14))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 0))
        _label(head, "Activation", 13, True, TXT).pack(side="left")
        self.lbl_state = ctk.CTkLabel(head, text="", width=120, height=22,
                                      corner_radius=11, font=F(10, True))
        self.lbl_state.pack(side="left", padx=12)

        col = ctk.CTkFrame(card, fg_color="transparent")
        col.pack(anchor="w", padx=20, pady=(12, 18))
        self._col = col
        W = 340

        # سطر تاريخ الانتهاء (بيظهر فقط لما يكون البرنامج مفعّل)
        self.lbl_expiry = _label(card, "", 12, True, GREEN)

        self.ent_lic = ctk.CTkEntry(col, width=W, height=40, corner_radius=20,
                                    border_width=1, border_color="#D5DEE8",
                                    fg_color="#FFFFFF", text_color=MUTED,
                                    placeholder_text="XXXXX_XXXXX_XXXXX_XXXXX-XXXXX",
                                    placeholder_text_color=MUTED2, font=F(12),
                                    justify="center")
        self.ent_lic.pack(pady=(0, 10))

        self.btn_remove = ctk.CTkButton(col, text="Remove", width=W, height=40,
                                        corner_radius=20, font=F(13),
                                        fg_color="#FFFFFF", hover_color=BLUE_BG,
                                        text_color=ACCENT, border_width=2,
                                        border_color=ACCENT,
                                        command=self.remove)
        self.btn_remove.pack(pady=(0, 10))

        self.btn_upgrade = ctk.CTkButton(col, text="Upgrade", width=W, height=40,
                                         corner_radius=20, font=F(13),
                                         fg_color=ACCENT, hover_color=ACCENT_H,
                                         text_color="#FFFFFF",
                                         command=self.activate)
        self.btn_upgrade.pack()

        self.lbl_msg = _label(col, "", 11, False, MUTED)
        self.lbl_msg.pack(anchor="w", pady=(8, 0))

        self.refresh()

    # ───────── المنطق ─────────
    def _msg(self, text, color=MUTED):
        try:
            if self.lbl_msg.winfo_exists():
                self.lbl_msg.configure(text=text, text_color=color)
        except Exception:
            pass

    def refresh(self):
        key = self.cfg.get("license", {}).get("key", "")
        on = LX.is_valid(key)
        self.ent_lic.configure(state="normal")
        self.ent_lic.delete(0, "end")
        if on:
            self.ent_lic.insert(0, LX.mask(key))
            self.ent_lic.configure(state="disabled")
            self.btn_upgrade.configure(text="Activated ✓", state="disabled")
            self.lbl_state.configure(text="ACTIVATED", fg_color=GREEN_BG, text_color=GREEN)
            text, color = _expiry_info(key)
            self.lbl_expiry.configure(text=text, text_color=color)
            self.lbl_expiry.pack_forget()
            self.lbl_expiry.pack(anchor="w", padx=20, pady=(10, 0), before=self._col)
        else:
            self.btn_upgrade.configure(text="Upgrade", state="normal")
            self.lbl_state.configure(text="NOT ACTIVATED", fg_color=CARD2, text_color=MUTED2)
            self.lbl_expiry.pack_forget()

    def activate(self):
        key = LX.normalize(self.ent_lic.get())
        if not key or not LX.is_valid(key):
            self._msg("Invalid license key.", RED)
            return
        self.cfg["license"] = {"key": key}
        if save_config(self.cfg):
            self.refresh()
            self._msg("Activated successfully ✓", GREEN)
        else:
            self._msg("Couldn't save the license.", RED)

    def remove(self):
        if LX.is_activated(self.cfg):
            self._confirm_remove()          # تحذير قبل الحذف
        else:
            self.ent_lic.delete(0, "end")
            self._msg("", MUTED)

    def _do_remove(self):
        self.cfg.pop("license", None)
        save_config(self.cfg)
        self.refresh()
        self._msg("License removed.", MUTED)

    def _confirm_remove(self):
        """نافذة تحذير: 'Do you want to remove it now?'"""
        try:
            old = getattr(self, "_dlg", None)
            if old is not None and old.winfo_exists():
                old.lift()
                old.focus_force()
                return
        except Exception:
            pass

        root = self.parent.winfo_toplevel()
        W, H = 420, 300
        dlg = ctk.CTkToplevel(root)
        self._dlg = dlg
        dlg.title("DeskControl Pro")
        dlg.resizable(False, False)
        dlg.configure(fg_color="#FFFFFF")
        try:
            root.update_idletasks()
            x = root.winfo_rootx() + (root.winfo_width() - W) // 2
            y = root.winfo_rooty() + (root.winfo_height() - H) // 2
        except Exception:
            x, y = 240, 140
        dlg.geometry(f"{W}x{H}+{max(x, 0)}+{max(y, 0)}")
        dlg.attributes("-topmost", True)

        def confirm():
            dlg.destroy()
            self._do_remove()

        ctk.CTkFrame(dlg, height=6, corner_radius=0, fg_color=RED).pack(fill="x")
        body = ctk.CTkFrame(dlg, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(24, 22))

        badge = ctk.CTkFrame(body, width=64, height=64, corner_radius=32,
                             fg_color=RED_BG)
        badge.pack()
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text="!", font=F(30, True), text_color=RED).pack(expand=True)

        _label(body, "Remove activation?", 20, True, TXT).pack(pady=(16, 6))
        _label(body, "Do you want to remove it now?\n"
                     "You won't be able to connect until you activate again.",
               12, False, MUTED, justify="center").pack()

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(side="bottom", fill="x", pady=(16, 0))
        btns.grid_columnconfigure((0, 1), weight=1, uniform="b")
        ctk.CTkButton(btns, text="Cancel", height=44, corner_radius=12,
                      font=F(13, True), fg_color="#FFFFFF", hover_color=BLUE_BG,
                      text_color=ACCENT, border_width=2, border_color=ACCENT,
                      command=dlg.destroy).grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(btns, text="Remove", height=44, corner_radius=12,
                      font=F(13, True), fg_color=RED, hover_color="#C9475B",
                      text_color="#FFFFFF", command=confirm
                      ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

        dlg.after(120, lambda: (dlg.lift(), dlg.focus_force()))


def build_activation_tab(parent, cfg):
    """نقطة الدخول من main.py: بتبني صفحة Activation وبترجع الكائن."""
    return ActivationTab(parent, cfg)