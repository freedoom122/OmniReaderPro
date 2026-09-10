#!/usr/bin/env python3
"""Developer launcher: python run_omnireader.py [files...]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from omnireader_pro.main import main

if __name__ == "__main__":
    main()
