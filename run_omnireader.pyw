# OmniReader Pro — windowed launcher (no console).
# Used by PyInstaller as the script target; also works with plain pythonw.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from omnireader_pro.main import main

if __name__ == "__main__":
    main()
