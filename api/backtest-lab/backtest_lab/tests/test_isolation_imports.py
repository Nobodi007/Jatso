"""กฎแยกขาด: แพ็กเกจนี้ต้องไม่ import/ผูกกับ Backtest เดิมหรือโค้ด Jatso ใด ๆ"""
import ast
import pathlib
import sys

PKG = pathlib.Path(__file__).resolve().parents[1]
ALLOWED_THIRD_PARTY = {"jwt", "fastapi", "yfinance", "pytest", "pandas", "numpy"}
FORBIDDEN_NAMES = {"api", "stocks", "simple_backtest", "bot_rules", "server", "App"}


def py_files():
    return [p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_imports_outside_package():
    stdlib = set(sys.stdlib_module_names)
    offenders = []
    for f in py_files():
        rel = f.relative_to(PKG.parent)
        pkg_parts = list(rel.parent.parts)                                   # เช่น ['backtest_lab', 'data']
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = pkg_parts[:len(pkg_parts) - (node.level - 1)]
                    if not base or base[0] != "backtest_lab":
                        offenders.append((str(rel), "relative import ออกนอกแพ็กเกจ"))
                    continue
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for n in names:
                if n in ("backtest_lab",) or n in stdlib or n in ALLOWED_THIRD_PARTY:
                    continue
                offenders.append((str(rel), n))
            for n in names:
                if n in FORBIDDEN_NAMES:
                    offenders.append((str(rel), f"forbidden:{n}"))
    assert not offenders, offenders


def test_package_has_no_dynamic_import_of_legacy_code():
    for f in py_files():
        if f.name == "test_isolation_imports.py":
            continue
        src = f.read_text(encoding="utf-8")
        for bad in ("importlib", "__import__", "api.stocks", "simple_backtest", "bot_rules"):
            for line in src.splitlines():
                code = line.split("#")[0]
                if bad in code and not code.strip().startswith(('"""', "'", '"')) and "import" in code:
                    raise AssertionError(f"{f.name}: {line.strip()}")
