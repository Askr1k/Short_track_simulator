"""Top-level launcher for the Short Track Sim project."""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from short_track.game import Game

if __name__ == "__main__":
    Game().run()
