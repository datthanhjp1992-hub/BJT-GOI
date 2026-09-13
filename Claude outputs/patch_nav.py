import re, glob, os

folder = os.environ["HTML_DIR"]
pattern = re.compile(r'(<a href="SC06_KiemTra_([ABC])\.html">Kiểm tra</a>\s*)(<a href="SC10_LuyenVietPdf_\2\.html">Luyện viết</a>)')

changed = []
for path in glob.glob(os.path.join(folder, "SC*.html")):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if "SC11_GopYTuVung" in content:
        continue
    def repl(m):
        theme = m.group(2)
        return f'{m.group(1)}<a href="SC11_GopYTuVung_{theme}.html">Góp ý</a>\n    {m.group(3)}'
    new_content, n = pattern.subn(repl, content)
    if n:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        changed.append(os.path.basename(path))

print("Patched:", changed)
