from __future__ import annotations

from pathlib import Path

from flux_mine.plc.l5k import parse_l5k_file
from flux_mine.plc.l5x import parse_l5x_file
from flux_mine.plc.models import PlcProject


def parse_plc_file(path: str | Path) -> PlcProject:
    source_path = Path(path)
    suffix = source_path.suffix.lower()
    if suffix == ".l5x":
        return parse_l5x_file(source_path)
    if suffix == ".l5k":
        return parse_l5k_file(source_path)
    raise ValueError(f"Unsupported PLC source file extension: {source_path.suffix or '<none>'}")
