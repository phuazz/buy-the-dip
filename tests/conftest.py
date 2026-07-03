import sys
from pathlib import Path

# Make `from scripts import ...` resolve when pytest runs from the repo root
# or from anywhere else.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
