import ast, sys
with open("remotedesk.py","r",encoding="utf-8") as f: src=f.read()
try:
    ast.parse(src)
    print("Syntax OK")
except SyntaxError as e:
    print(f"ERROR line {e.lineno}: {e.msg}"); sys.exit(1)

checks=[
    ("_draw_bg",         "draw_bg function"),
    ("_bg_canvas",       "bg canvas"),
    ("create_rectangle", "rectangle gradient"),
    ("create_oval",      "circles"),
    ("create_line",      "lines"),
    ("d7ecf9",           "bg color"),
    ("transparent",      "transparent body"),
]
ok=True
for v,l in checks:
    f=v in src
    if not f: ok=False
    print(f"  {'OK  ' if f else 'MISS'} {l}")
print("ALL OK" if ok else "ISSUES")
