#!/usr/bin/env python3
"""Remove the generated static bundle before building it again."""

import shutil
from pathlib import Path

web_root = Path(__file__).resolve().parents[2] / "web"
dist = web_root / "dist"
if dist.is_symlink() or dist.resolve().parent != web_root:
    raise SystemExit("Refusing to clean outside web/dist")
if dist.exists():
    shutil.rmtree(dist)
