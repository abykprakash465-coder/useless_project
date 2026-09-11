import tokenize
import io

with open("desktop_cat.py", "r", encoding="utf-8") as f:
    source = f.read()

comments_to_remove = []
with io.BytesIO(source.encode("utf-8")) as f:
    for tok in tokenize.tokenize(f.readline):
        if tok.type == tokenize.COMMENT:
            if "feed" not in tok.string.lower():
                comments_to_remove.append((tok.start, tok.end))

lines = source.splitlines(True)
for start, end in reversed(comments_to_remove):
    s_row, s_col = start
    e_row, e_col = end
    row = s_row - 1
    line = lines[row]
    lines[row] = line[:s_col] + line[e_col:]
    if lines[row].strip() == "":
        lines[row] = ""

with open("desktop_cat.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
