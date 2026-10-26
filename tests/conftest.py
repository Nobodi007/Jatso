import pathlib
import sys

# tests import the stock package as `stocks` (relative imports inside); make api/ importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "api"))
