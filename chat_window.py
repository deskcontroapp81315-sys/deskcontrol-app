# chat_window.py - شات بسيط للطرفين
import time
import customtkinter as ctk
from config import F


def is_alive(win):
    try:
        return win is not None and bool(win.winfo_exists())
    except Exception:
        return False


class ChatWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_send_cb, title="Chat"):
        super().__init__(parent)
        self.on_send_cb = on_send_cb
        self.title(title)
        self.geometry("360x480")
        self.minsize(300, 360)
        self.configure(fg_color="#F5F9FD")

        self.log = ctk.CTkTextbox(self, wrap="word", fg_color="#FFFFFF", text_color="#10243E",
                                  border_width=1, border_color="#E2EDF7", corner_radius=12,
                                  font=F(13))
        self.log.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        self.log.tag_config("me", foreground="#1A9BE6")
        self.log.tag_config("them", foreground="#17B26A")
        self.log.configure(state="disabled")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))
        self.entry = ctk.CTkEntry(row, placeholder_text="Type a message…", height=38,
                                  corner_radius=10, font=F(13))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self._send())
        ctk.CTkButton(row, text="Send", width=80, height=38, corner_radius=10,
                      font=F(13, True), fg_color="#1A9BE6", hover_color="#1589CC",
                      command=self._send).pack(side="left", padx=(8, 0))

        self.after(250, self._focus_entry)

    def _focus_entry(self):
        try:
            self.entry.focus()
        except Exception:
            pass

    def _send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.add_message("Me", text, mine=True)
        try:
            self.on_send_cb(text)
        except Exception:
            pass

    def add_message(self, who, text, mine=False):
        stamp = time.strftime("%H:%M")
        self.log.configure(state="normal")
        self.log.insert("end", f"{who} · {stamp}\n", "me" if mine else "them")
        self.log.insert("end", text + "\n\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    def pop(self):
        """يطلّع النافذة قدّام (لما توصل رسالة جديدة)."""
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
        except Exception:
            pass