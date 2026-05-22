"""Self-contained test configuration — tests work without PYTHONPATH."""
from __future__ import annotations

import os
import sys

# Add src to sys.path so imports work without pip install -e or PYTHONPATH
_src = os.path.join(os.path.dirname(__file__), "..", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
