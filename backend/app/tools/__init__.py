"""Tools package. Explicitly loads submodules so 9p directory caching never hides new tool files."""
import importlib.util
import sys
from pathlib import Path

_DIR = Path(__file__).parent
for _name in ("calc", "diagram", "docx_builder", "image", "pdf_builder", "pptx_builder", "science_plot"):
    _full = f"{__name__}.{_name}"
    _path = _DIR / f"{_name}.py"
    if _full not in sys.modules and _path.exists():
        _spec = importlib.util.spec_from_file_location(_full, _path)
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules[_full] = _mod
            _spec.loader.exec_module(_mod)
            globals()[_name] = _mod
