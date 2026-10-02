"""Macht das Paket `core` importierbar, ohne den Integrationsordner selbst in sys.path zu legen.

Im Integrationsordner liegen select.py, text.py, number.py usw. Würde er in sys.path stehen, überdeckten sie
Module der Standardbibliothek (z. B. `select`) und die Tests würden beim Import scheitern.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

_core = Path(__file__).resolve().parents[1] / "custom_components" / "reisekosten" / "core"
_tmp = tempfile.mkdtemp()
os.symlink(_core, os.path.join(_tmp, "core"), target_is_directory=True)
sys.path.insert(0, _tmp)
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)
