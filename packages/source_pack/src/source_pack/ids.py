from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid5

NAMESPACE = UUID("7b4d4a56-91ab-54fa-9a91-05bb47930777")


def stable_uuid(value: str) -> UUID:
    return uuid5(NAMESPACE, value)


def slug_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^\d+_", "", stem)
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
