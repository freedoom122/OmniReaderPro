#!/usr/bin/env python3
"""Developer launcher: python run_veyrion.py [files...]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from veyrion_workspace.main import main

if __name__ == "__main__":
    main()
