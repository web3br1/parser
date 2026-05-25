import sys
from pathlib import Path

# Add all workspace source directories so tests work without `uv sync`
_root = Path(__file__).parent
_src_paths = [
    _root / "apps" / "api" / "src",
    _root / "workers" / "ingest" / "src",
    _root / "workers" / "classification" / "src",
    _root / "workers" / "extraction" / "src",
    _root / "workers" / "review" / "src",
    _root / "workers" / "sync" / "src",
    _root / "packages" / "normalizers" / "src",
    _root / "packages" / "parsers" / "src",
    _root / "packages" / "schema_registry" / "src",
    _root / "packages" / "model_gateway" / "src",
    _root / "packages" / "domain" / "src",
    _root / "packages" / "security" / "src",
    _root / "packages" / "observability" / "src",
    _root / "packages" / "source_pack" / "src",
]
for p in _src_paths:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
