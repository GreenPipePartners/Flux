from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OPENPLC_EDITOR_ROOT_ENV = "FLUX_DEEP_OPENPLC_EDITOR_ROOT"


@dataclass(frozen=True)
class OpenPlcEditorGenerateResult:
    source_path: Path
    st_text: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class OpenPlcEditorToolchain:
    root: Path

    @classmethod
    def from_env(cls) -> "OpenPlcEditorToolchain | None":
        import os

        value = os.environ.get(OPENPLC_EDITOR_ROOT_ENV, "").strip()
        if not value:
            return None
        toolchain = cls(Path(value))
        return toolchain if toolchain.is_available() else None

    @property
    def editor_dir(self) -> Path:
        nested = self.root / "editor"
        return nested if nested.exists() else self.root

    def is_available(self) -> bool:
        return (self.editor_dir / "PLCGenerator.py").exists() and (
            self.editor_dir / "plcopen" / "plcopen.py"
        ).exists()

    def generate_st(self, plc_xml_path: str | Path) -> OpenPlcEditorGenerateResult:
        if not self.is_available():
            raise FileNotFoundError(
                "OpenPLC Editor toolchain is unavailable. Set FLUX_DEEP_OPENPLC_EDITOR_ROOT "
                "to an OpenPLC_Editor checkout or its editor directory."
            )

        source = Path(plc_xml_path)
        if not source.exists():
            raise FileNotFoundError(source)

        _install_wx_stub()
        _prepend_sys_path(self.editor_dir)

        try:
            from PLCGenerator import GenerateCurrentProgram
            from plcopen import LoadProject
            from plcopen.structures import StdBlckLst, TypeHierarchy
        except ModuleNotFoundError as exc:
            if exc.name == "lxml":
                raise RuntimeError("OpenPLC Editor generation requires optional dependency lxml") from exc
            raise

        project, load_error = LoadProject(str(source))
        if project is None:
            raise RuntimeError(f"OpenPLC Editor rejected plc.xml: {load_error}")

        errors: list[Any] = []
        warnings: list[Any] = []
        controler = _HeadlessEditorControler(project, TypeHierarchy, StdBlckLst)
        chunks = GenerateCurrentProgram(controler, project, errors, warnings)
        return OpenPlcEditorGenerateResult(
            source_path=source,
            st_text="".join(item[0] for item in chunks),
            errors=tuple(str(error) for error in errors),
            warnings=tuple(str(warning) for warning in warnings),
        )


class _HeadlessEditorControler:
    """Minimal PLCGenerator controler surface for headless PLCopen LD validation."""

    def __init__(self, project: Any, type_hierarchy: dict[str, str], std_block_list: list[dict[str, Any]]) -> None:
        self.Project = project
        self.TypeHierarchy = type_hierarchy
        self.TotalTypesDict: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for section in std_block_list:
            for block in section["list"]:
                self.TotalTypesDict.setdefault(block["name"], []).append((section["name"], block))

    def GetProject(self, debug: bool = False) -> Any:
        return self.Project

    def GetConfigurationExtraVariables(self) -> list[Any]:
        return []

    def GetDataType(self, typename: str, debug: bool = False) -> Any:
        if self.Project is None:
            return None
        return self.Project.getdataType(typename)

    def GetDataTypeBaseType(self, datatype: Any) -> str:
        content = datatype.baseType.getcontent()
        kind = content.getLocalTag()
        if kind in {"array", "subrangeSigned", "subrangeUnsigned"}:
            base = content.baseType.getcontent()
            base_kind = base.getLocalTag()
            return base.getname() if base_kind == "derived" else base_kind.upper()
        return content.getname() if kind == "derived" else kind.upper()

    def GetBaseType(self, typename: str, debug: bool = False) -> str | None:
        if typename in self.TypeHierarchy:
            return typename
        datatype = self.GetDataType(typename, debug)
        if datatype is not None:
            base = self.GetDataTypeBaseType(datatype)
            return self.GetBaseType(base, debug) if base is not None else typename
        return None

    def IsOfType(self, typename: str, reference: str | None, debug: bool = False) -> bool:
        if reference is None or typename == reference:
            return True
        base = self.TypeHierarchy.get(typename)
        if base is not None:
            return self.IsOfType(base, reference)
        datatype = self.GetDataType(typename, debug)
        if datatype is not None:
            base = self.GetDataTypeBaseType(datatype)
            if base is not None:
                return self.IsOfType(base, reference, debug)
        return False

    def GetBlockType(
        self,
        typename: str,
        inputs: tuple[str, ...] | str | None = None,
        debug: bool = False,
    ) -> dict[str, Any] | None:
        result_blocktype: dict[str, Any] = {}
        for _section, blocktype in self.TotalTypesDict.get(typename, []):
            if inputs is not None and inputs != "undefined":
                block_inputs = tuple(var_type for _name, var_type, _modifier in blocktype["inputs"])
                if all(
                    actual == "ANY" or self.IsOfType(actual, expected)
                    for actual, expected in zip(inputs, block_inputs, strict=False)
                ):
                    return blocktype
            else:
                if result_blocktype:
                    if inputs == "undefined":
                        return None
                    result_blocktype["inputs"] = [(i[0], "ANY", i[2]) for i in result_blocktype["inputs"]]
                    result_blocktype["outputs"] = [(o[0], "ANY", o[2]) for o in result_blocktype["outputs"]]
                    return result_blocktype
                result_blocktype = blocktype.copy()
        if result_blocktype:
            return result_blocktype
        if self.Project is not None:
            pou = self.Project.getpou(typename)
            if pou is not None:
                return pou.getblockInfos()
        return None

    def GetDataTypeInfos(self, tagname: str, debug: bool = False) -> None:
        return None


def _install_wx_stub() -> None:
    if "wx" in sys.modules:
        return
    wx = types.ModuleType("wx")
    wx.GetTranslation = lambda text: text
    sys.modules["wx"] = wx


def _prepend_sys_path(path: Path) -> None:
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


__all__ = [
    "OPENPLC_EDITOR_ROOT_ENV",
    "OpenPlcEditorGenerateResult",
    "OpenPlcEditorToolchain",
]
