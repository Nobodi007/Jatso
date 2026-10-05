from pathlib import Path

ROOT = Path("src")
EXTS = {".tsx", ".ts", ".css", ".html"}

def is_mojibake(s):
    markers = [
        "à¸", "à¹", "â‚", "â€”", "â€“",
        "Ã", "Â", "ðŸ", "ï»¿"
    ]
    return sum(s.count(x) for x in markers) >= 2

for path in ROOT.rglob("*"):
    if path.suffix.lower() not in EXTS or not path.is_file():
        continue

    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        continue

    if not is_mojibake(text):
        continue

    try:
        fixed = text.encode("latin1").decode("utf-8")
    except Exception:
        continue

    path.write_text(fixed, encoding="utf-8", newline="")
    print("FIXED:", path)

print("DONE")
