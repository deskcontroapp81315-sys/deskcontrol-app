# file_manager.py - مدير ملفات بقسمين (Local / Remote)
import os
import shutil
import threading
from tkinter import ttk, messagebox
import tkinter as tk
import customtkinter as ctk

from config import F
from fs_utils import (DRIVES, list_dir, parent_of, join_path, fmt_date,
                      fmt_size, file_type, send_file)

ACCENT = "#1A9BE6"
ACCENT_H = "#1589CC"
ACCENT_LT = "#8EC9F0"
TXT = "#10243E"
MUTED = "#44566B"
RED = "#E0556A"


class Pane(ctk.CTkFrame):
    COLS = (("name", "Name", 230, "w"), ("date", "Date modified", 150, "w"),
            ("type", "Type", 100, "w"), ("size", "Size", 80, "e"))

    def __init__(self, parent, title, action_text, on_go, on_action, on_mkdir, on_delete):
        super().__init__(parent, fg_color="transparent")
        self.on_go = on_go
        self.on_action = on_action
        self.path = ""
        self.items = []
        self.sort_col = "name"
        self.sort_rev = False

        ctk.CTkLabel(self, text=title, font=F(14, True), text_color=TXT).pack(anchor="w", pady=(0, 10))

        r1 = ctk.CTkFrame(self, fg_color="transparent")
        r1.pack(fill="x")
        ctk.CTkButton(r1, text="↑", width=38, height=38, corner_radius=10, font=F(18, True),
                      fg_color="#FFFFFF", text_color=ACCENT, hover_color="#E8F4FD",
                      border_width=2, border_color=ACCENT,
                      command=lambda: self.on_go(parent_of(self.path))).pack(side="left")
        self.entry = ctk.CTkEntry(r1, height=36, corner_radius=18, border_width=1,
                                  border_color="#9AA9B8", fg_color="#FFFFFF",
                                  text_color=TXT, font=F(12))
        self.entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.entry.bind("<Return>", self._enter)

        r2 = ctk.CTkFrame(self, fg_color="transparent")
        r2.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(r2, text="📁 New folder", width=110, height=32, corner_radius=10,
                      font=F(12, True), fg_color="#FFFFFF", text_color=ACCENT,
                      hover_color="#E8F4FD", border_width=1, border_color=ACCENT,
                      command=on_mkdir).pack(side="left")
        ctk.CTkButton(r2, text="🗑 Delete", width=90, height=32, corner_radius=10,
                      font=F(12, True), fg_color="#FFFFFF", text_color=RED,
                      hover_color="#FDEEF0", border_width=1, border_color=RED,
                      command=lambda: on_delete(self.selected_items())).pack(side="left", padx=8)
        self.btn_action = ctk.CTkButton(r2, text=action_text, width=140, height=34, corner_radius=17,
                                        font=F(12, True), fg_color=ACCENT_LT, hover_color=ACCENT_H,
                                        state="disabled",
                                        command=lambda: self.on_action(self.selected_items()))
        self.btn_action.pack(side="right")

        wrap = tk.Frame(self, bg="#FFFFFF", highlightthickness=1, highlightbackground="#B9C7D4")
        wrap.pack(fill="both", expand=True, pady=(10, 0))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="headings",
                                 selectmode="extended", style="Files.Treeview")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for cid, text, width, anchor in self.COLS:
            self.tree.heading(cid, text=text, anchor="w",
                              command=lambda c=cid: self._sort_by(c))
            self.tree.column(cid, width=width, anchor=anchor, stretch=(cid == "name"))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double)

    # ── التنقل ──
    def _enter(self, _e=None):
        p = self.entry.get().strip()
        if p.lower() == "drives":
            p = DRIVES
        self.on_go(p)

    def _show_path(self):
        self.entry.delete(0, "end")
        self.entry.insert(0, "Drives" if self.path == DRIVES else self.path)

    def restore(self):
        self._show_path()

    def set_items(self, path, items):
        self.path = path
        self._show_path()
        self.items = items
        self._fill()

    # ── الجدول ──
    def _key(self, it):
        c = self.sort_col
        if c == "name":
            return it["name"].lower()
        if c == "date":
            return it["mtime"]
        if c == "type":
            return file_type(it).lower()
        return it["size"]

    def _fill(self):
        dirs = sorted([i for i in self.items if i["dir"]], key=self._key, reverse=self.sort_rev)
        files = sorted([i for i in self.items if not i["dir"]], key=self._key, reverse=self.sort_rev)
        self.items = dirs + files
        self.tree.delete(*self.tree.get_children())
        for idx, it in enumerate(self.items):
            icon = "📁 " if it["dir"] else "📄 "
            size = "" if it["dir"] else fmt_size(it["size"])
            self.tree.insert("", "end", iid=str(idx),
                             values=(icon + it["name"], fmt_date(it["mtime"]), file_type(it), size))
        self._on_select()

    def _sort_by(self, col):
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col, self.sort_rev = col, False
        self._fill()

    def selected_items(self):
        out = []
        for iid in self.tree.selection():
            i = int(iid)
            if i < len(self.items):
                out.append(self.items[i])
        return out

    def _on_select(self, _e=None):
        if self.tree.selection():
            self.btn_action.configure(state="normal", fg_color=ACCENT)
        else:
            self.btn_action.configure(state="disabled", fg_color=ACCENT_LT)

    def _on_double(self, e):
        row = self.tree.identify_row(e.y)
        if not row:
            return
        it = self.items[int(row)]
        if it["dir"]:
            self.on_go(it["name"] if self.path == DRIVES else join_path(self.path, it["name"]))


class FileManagerWindow(ctk.CTkToplevel):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.title(f"{viewer.dev_id} - File Manager")
        self.geometry("1040x640")
        self.minsize(820, 480)
        self.configure(fg_color="#FFFFFF")

        self._status = "Ready"
        self._shown = ""
        self._progress = 0.0
        self._local_dirty = False
        self._busy_up = False

        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Files.Treeview", font=("Segoe UI", 10), rowheight=24, background="#FFFFFF",
                     fieldbackground="#FFFFFF", foreground=TXT, borderwidth=0)
        st.configure("Files.Treeview.Heading", font=("Segoe UI", 10), background="#FFFFFF",
                     foreground=TXT, relief="flat")
        st.map("Files.Treeview", background=[("selected", "#CDE8FA")],
               foreground=[("selected", TXT)])

        self.grid_columnconfigure((0, 1), weight=1, uniform="p")
        self.grid_rowconfigure(0, weight=1)

        self.local = Pane(self, "Local", "Upload", self.go_local, self.upload,
                          self.mkdir_local, self.delete_local)
        self.local.grid(row=0, column=0, sticky="nsew", padx=(14, 7), pady=(12, 0))
        self.remote = Pane(self, "Remote", "Download", self.go_remote, self.download,
                           self.mkdir_remote, self.delete_remote)
        self.remote.grid(row=0, column=1, sticky="nsew", padx=(7, 14), pady=(12, 0))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=10)
        self.lbl = ctk.CTkLabel(bar, text="Ready", font=F(12), text_color=MUTED, anchor="w")
        self.lbl.pack(side="left", fill="x", expand=True)
        self.bar = ctk.CTkProgressBar(bar, width=240, progress_color=ACCENT)
        self.bar.set(0)
        self.bar.pack(side="right")

        self.go_local("")
        self.go_remote("")
        self._tick()

    # ───────── حالة وتحديث ─────────
    def _tick(self):
        try:
            if self._status != self._shown:
                self.lbl.configure(text=self._status)
                self._shown = self._status
            self.bar.set(self._progress)
            if self._local_dirty:
                self._local_dirty = False
                self.go_local(self.local.path)
            self.after(150, self._tick)
        except Exception:
            pass

    def _prog(self, text, got, size):
        pct = int(got * 100 / size) if size else 100
        self._status = f"{text}  {pct}%"
        self._progress = (got / size) if size else 1.0

    # ───────── من الـ Viewer (بالخيط الرئيسي) ─────────
    def on_message(self, msg):
        t = msg.get("t")
        if t == "fs_list":
            if msg.get("err"):
                self._status = "Remote: " + msg["err"]
                self.remote.restore()
            else:
                self.remote.set_items(msg["path"], msg["items"])
        elif t == "fs_res":
            if msg.get("ok"):
                self._status = "Done"
                self.go_remote(self.remote.path)
            else:
                self._status = "Remote error: " + msg.get("err", "")
        elif t == "fs_done" and not msg.get("ok"):
            self._status = "Transfer failed: " + msg.get("err", "")

    def on_progress(self, verb, name, got, size):
        self._prog(f"{verb} {name}", got, size)

    def on_download_done(self, path):
        self._status = f"Downloaded {os.path.basename(path)}"
        self._progress = 0
        self._local_dirty = True

    # ───────── التنقل ─────────
    def go_local(self, path):
        p, items, err = list_dir(path)
        if err:
            self._status = "Local: " + err
            self.local.restore()
            return
        self.local.set_items(p, items)

    def go_remote(self, path):
        self.viewer.send({"t": "fs_list", "path": path})

    # ───────── رفع ─────────
    def upload(self, items):
        remote_dir, local_dir = self.remote.path, self.local.path
        if not remote_dir or remote_dir == DRIVES or local_dir == DRIVES:
            self._status = "Open a folder on both sides first."
            return
        if self._busy_up:
            self._status = "An upload is already running."
            return
        jobs = []
        for it in items:
            src = os.path.join(local_dir, it["name"])
            if it["dir"]:
                for root, _, files in os.walk(src):
                    for fn in files:
                        full = os.path.join(root, fn)
                        rel = os.path.relpath(full, local_dir).replace("\\", "/").split("/")
                        jobs.append((full, rel))
            else:
                jobs.append((src, [it["name"]]))
        if not jobs:
            self._status = "Nothing to upload."
            return
        threading.Thread(target=self._upload_worker, args=(jobs, remote_dir), daemon=True).start()

    def _upload_worker(self, jobs, remote_dir):
        self._busy_up = True
        done = 0
        try:
            total = len(jobs)
            for i, (full, parts) in enumerate(jobs, 1):
                dest = remote_dir
                for p in parts:
                    dest = join_path(dest, p)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                tid = self.viewer.next_id()
                self.viewer.send({"t": "fs_put", "id": tid, "path": dest, "size": size})
                send_file(self.viewer.conn, tid, full,
                          progress=lambda t, g, s, n, i=i: self._prog(f"Uploading {n} ({i}/{total})", g, s))
                done += 1
            self._status = f"Uploaded {done} file(s)"
        except Exception as e:
            self._status = f"Upload failed: {e}"
        finally:
            self._busy_up = False
            self._progress = 0
            self.viewer.send({"t": "fs_list", "path": remote_dir})

    # ───────── تنزيل ─────────
    def download(self, items):
        local_dir, remote_dir = self.local.path, self.remote.path
        if not local_dir or local_dir == DRIVES or not remote_dir or remote_dir == DRIVES:
            self._status = "Open a folder on both sides first."
            return
        for it in items:
            rid = self.viewer.next_id()
            self.viewer.dl_targets[rid] = local_dir
            self.viewer.send({"t": "fs_get", "id": rid, "path": join_path(remote_dir, it["name"])})
        self._status = "Downloading…"

    # ───────── مجلد جديد / حذف ─────────
    def _ask_name(self):
        dlg = ctk.CTkInputDialog(text="Folder name:", title="New folder")
        name = dlg.get_input()
        return name.strip() if name else ""

    def mkdir_local(self):
        if self.local.path == DRIVES:
            return
        name = self._ask_name()
        if not name:
            return
        try:
            os.mkdir(os.path.join(self.local.path, name))
            self.go_local(self.local.path)
        except Exception as e:
            self._status = f"Local: {e}"

    def mkdir_remote(self):
        if self.remote.path == DRIVES:
            return
        name = self._ask_name()
        if name:
            self.viewer.send({"t": "fs_mkdir", "path": join_path(self.remote.path, name)})

    def delete_local(self, items):
        if not items or self.local.path == DRIVES:
            return
        if not messagebox.askyesno("Delete", f"Delete {len(items)} item(s) from this device?", parent=self):
            return
        errs = []
        for it in items:
            p = os.path.join(self.local.path, it["name"])
            try:
                if it["dir"]:
                    shutil.rmtree(p)
                else:
                    os.remove(p)
            except Exception as e:
                errs.append(str(e))
        self._status = ("Local: " + "; ".join(errs)) if errs else "Deleted"
        self.go_local(self.local.path)

    def delete_remote(self, items):
        if not items or self.remote.path == DRIVES:
            return
        if not messagebox.askyesno("Delete", f"Delete {len(items)} item(s) from the remote device?", parent=self):
            return
        paths = [join_path(self.remote.path, it["name"]) for it in items]
        self.viewer.send({"t": "fs_delete", "paths": paths})