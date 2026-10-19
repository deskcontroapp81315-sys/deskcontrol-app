# fs_helper.py
import os, sys, string, shutil

def fs_roots(home=None):[cite: 4]
    home = home or os.path.expanduser("~")
    quick = [{"label": os.path.basename(home.rstrip("/\\")) or home, "path": home}]
    for sub in ("Desktop", "Documents", "Downloads"):
        p = os.path.join(home, sub)
        if os.path.isdir(p): quick.append({"label": sub, "path": p})
    drives = []
    if sys.platform.startswith("win"):
        for L in string.ascii_uppercase:
            d = f"{L}:\\"
            if os.path.exists(d): drives.append(d)
    else: drives = ["/"]
    return {"home": home, "quick": quick, "drives": drives}

def fs_list(path):[cite: 4]
    abspath = os.path.abspath(path) if path else os.path.expanduser("~")
    entries = []
    with os.scandir(abspath) as it:
        for e in it:
            try:
                is_dir = e.is_dir(follow_symlinks=False)
                st = e.stat(follow_symlinks=False)
                entries.append({"name": e.name, "is_dir": is_dir, "size": 0 if is_dir else st.st_size, "mtime": st.st_mtime})
            except OSError: continue
    entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return abspath, entries