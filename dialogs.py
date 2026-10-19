# dialogs.py
import tkinter as tk
import customtkinter as ctk
from config import F
from utils import kill_win_animation

# ألوان مطابقة للوحة main.py
BLUE  = "#1A9BE6"
WHITE = "#FFFFFF"
RED   = "#E0556A"
GREEN = "#17B26A"
TXT_D = "#10243E"
TXT_M = "#44566B"


class ChatWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_send_cb):
        super().__init__(parent)
        self.title("الدردشة المباشرة")
        self.geometry("380x450")
        self.on_send_cb = on_send_cb
        kill_win_animation(self)

        self.txt_area = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.txt_area.pack(fill="both", expand=True, padx=10, pady=10)

        f_in = ctk.CTkFrame(self)
        f_in.pack(fill="x", padx=10, pady=(0, 10))

        self.entry = ctk.CTkEntry(f_in, placeholder_text="اكتب رسالتك هنا...")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry.bind("<Return>", lambda e: self.send())

        btn = ctk.CTkButton(f_in, text="إرسال", width=70, command=self.send)
        btn.pack(side="right")

    def send(self):
        msg = self.entry.get().strip()
        if msg:
            self.add_msg("أنا", msg)
            self.on_send_cb(msg)
            self.entry.delete(0, "end")

    def add_msg(self, sender, text):
        self.txt_area.configure(state="normal")
        self.txt_area.insert("end", f"{sender}: {text}\n")
        self.txt_area.configure(state="disabled")
        self.txt_area.see("end")


class ConsentDlg(ctk.CTkToplevel):
    def __init__(self, parent, dev_id, on_reply):
        super().__init__(parent)
        self.title("طلب اتصال وارد")
        self.geometry("360x200")
        self.on_reply = on_reply
        self.time_left = 30
        self._done = False
        kill_win_animation(self)

        # إظهار النافذة فوق الباقي وتركيز الانتباه عليها
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()

        lbl = ctk.CTkLabel(self, text=f"يرغب الجهاز ({dev_id})\nبالاتصال ببدء التحكم البعيد.",
                           font=F(14, True), text_color=TXT_D)
        lbl.pack(pady=20)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20)

        self.btn_acc = ctk.CTkButton(btns, text=f"قبول ({self.time_left})", fg_color=GREEN,
                                     hover_color="#139A5C", command=lambda: self.reply(True))
        self.btn_acc.pack(side="left", expand=True, padx=(0, 8))

        btn_rej = ctk.CTkButton(btns, text="رفض", fg_color=RED,
                                hover_color="#C94459", command=lambda: self.reply(False))
        btn_rej.pack(side="right", expand=True, padx=(8, 0))

        self.protocol("WM_DELETE_WINDOW", lambda: self.reply(False))
        self._tick()

    def _tick(self):
        if self._done:
            return
        if self.time_left > 0:
            self.time_left -= 1
            self.btn_acc.configure(text=f"قبول ({self.time_left})")
            self.after(1000, self._tick)
        else:
            self.reply(False)

    def reply(self, val):
        if self._done:
            return
        self._done = True
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_reply:
            self.on_reply(val)