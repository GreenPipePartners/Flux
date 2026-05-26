from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from flux_mine.imports import parse_import_bytes
from flux_mine.hmi.factorytalk import FactoryTalkProject
from flux_mine.plc.models import PlcProject


def test_parse_import_bytes_detects_l5x_upload() -> None:
    result = parse_import_bytes(
        "sample.L5X",
        b'<RSLogix5000Content><Controller Name="PLC_01"><Tags /></Controller></RSLogix5000Content>',
    )

    assert result.source_type == "plc_l5x"
    assert isinstance(result.project, PlcProject)
    assert result.project.controller_named("PLC_01") is not None


def test_parse_import_bytes_detects_l5k_upload() -> None:
    result = parse_import_bytes(
        "sample.L5K",
        b"""
        CONTROLLER PLC_01
            TAG
                Pressure : REAL;
            END_TAG
        """.strip(),
    )

    assert result.source_type == "plc_l5k"
    assert isinstance(result.project, PlcProject)
    assert result.project.controller_named("PLC_01") is not None


def test_parse_import_bytes_extracts_factorytalk_zip() -> None:
    result = parse_import_bytes(
        "ftv.zip",
        zip_bytes(
            {
                "Displays/Overview.xml": '<gfx><numericDisplay name="Pressure" left="1" top="2" tag="{[PLC]PT001}" /></gfx>',
                "Parameters/Overview.par": "#1=[PLC]PT001\n",
                "Graphics/Overview.gfx": "ignored binary placeholder",
            }
        ),
    )

    assert result.source_type == "factorytalk"
    assert isinstance(result.project, FactoryTalkProject)
    assert result.project.summary()["screen_count"] == 1
    assert result.project.summary()["parameter_file_count"] == 1
    assert result.project.screens[0].source_path == "ftv.zip:Displays/Overview.xml"
    assert result.import_summary["recognized_file_count"] == 2
    assert result.import_summary["ignored_file_count"] == 1


def test_parse_import_bytes_rejects_zip_traversal() -> None:
    with pytest.raises(ValueError, match="unsafe path"):
        parse_import_bytes("ftv.zip", zip_bytes({"../evil.xml": "<gfx />"}))


def test_parse_import_bytes_rejects_factorytalk_zip_without_known_inputs() -> None:
    with pytest.raises(ValueError, match="does not contain any .xml or .par"):
        parse_import_bytes("ftv.zip", zip_bytes({"readme.txt": "nothing useful"}))


def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
