from __future__ import annotations

import hashlib
import stat
import zipfile
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from flux_mine.hmi.factorytalk import (
    FactoryTalkParameterFile,
    FactoryTalkProject,
    FactoryTalkScreen,
    parse_factorytalk_directory,
    parse_factorytalk_path,
)
from flux_mine.plc.l5k import parse_l5k_text
from flux_mine.plc.l5x import parse_l5x_text
from flux_mine.plc.models import PlcProject
from flux_mine.plc.parsers import parse_plc_file


ProjectImport = PlcProject | FactoryTalkProject


@dataclass(frozen=True)
class ImportLimits:
    max_files: int = 5000
    max_total_uncompressed_bytes: int = 250 * 1024 * 1024
    max_single_file_bytes: int = 50 * 1024 * 1024


@dataclass(frozen=True)
class MineImport:
    source_type: str
    source_name: str
    source_sha256: str
    project: ProjectImport
    import_summary: dict[str, Any]


def parse_import_path(path: str | Path, *, source_type: str = "auto", limits: ImportLimits | None = None) -> MineImport:
    source_path = Path(path)
    resolved_type = resolve_import_source_type(source_path, source_type)
    if source_path.suffix.lower() == ".zip":
        result = parse_import_bytes(source_path.name, source_path.read_bytes(), source_type=resolved_type, limits=limits)
        project = replace(result.project, source_path=str(source_path))
        return replace(result, source_name=str(source_path), project=project)
    if resolved_type in {"plc_l5x", "plc_l5k"}:
        project = parse_plc_file(source_path)
        return MineImport(
            source_type=resolved_type,
            source_name=str(source_path),
            source_sha256=project.source_sha256,
            project=project,
            import_summary={"container": "file", "recognized_file_count": 1, "ignored_file_count": 0},
        )
    if resolved_type == "factorytalk":
        project = parse_factorytalk_path(source_path)
        return MineImport(
            source_type=resolved_type,
            source_name=str(source_path),
            source_sha256=project.source_sha256,
            project=project,
            import_summary=factorytalk_path_summary(source_path),
        )
    raise ValueError(f"Unsupported import source type: {resolved_type}")


def parse_import_bytes(
    filename: str,
    content: bytes,
    *,
    source_type: str = "auto",
    limits: ImportLimits | None = None,
) -> MineImport:
    source_name = Path(filename).name
    suffix = Path(source_name).suffix.lower()
    resolved_type = resolve_import_source_type(Path(source_name), source_type)
    source_sha256 = hashlib.sha256(content).hexdigest()
    if suffix == ".zip":
        if resolved_type != "factorytalk":
            raise ValueError("ZIP imports are only supported for FactoryTalk sources")
        project, summary = parse_factorytalk_zip_bytes(source_name, content, source_sha256=source_sha256, limits=limits)
        return MineImport(resolved_type, source_name, source_sha256, project, summary)
    if resolved_type == "plc_l5x":
        project = parse_l5x_text(content.decode("utf-8-sig", errors="replace"), source_path=source_name, source_sha256=source_sha256)
        return MineImport(
            resolved_type,
            source_name,
            source_sha256,
            project,
            {"container": "upload", "recognized_file_count": 1, "ignored_file_count": 0},
        )
    if resolved_type == "plc_l5k":
        project = parse_l5k_text(content.decode("utf-8-sig", errors="replace"), source_path=source_name, source_sha256=source_sha256)
        return MineImport(
            resolved_type,
            source_name,
            source_sha256,
            project,
            {"container": "upload", "recognized_file_count": 1, "ignored_file_count": 0},
        )
    raise ValueError(f"Unsupported uploaded import source: {source_name}")


def parse_factorytalk_zip_bytes(
    source_name: str,
    content: bytes,
    *,
    source_sha256: str,
    limits: ImportLimits | None = None,
) -> tuple[FactoryTalkProject, dict[str, Any]]:
    limits = limits or ImportLimits()
    with TemporaryDirectory(prefix="flux-factorytalk-") as temp_dir:
        extract_root = Path(temp_dir)
        with zipfile.ZipFile(BytesIO(content)) as archive:
            summary = extract_factorytalk_zip(archive, extract_root, limits=limits)
        if summary["recognized_file_count"] == 0:
            raise ValueError("FactoryTalk ZIP does not contain any .xml or .par files")
        project = parse_factorytalk_directory(extract_root)
        project = rewrite_factorytalk_project_paths(project, root=extract_root, source_name=source_name, source_sha256=source_sha256)
        summary["container"] = "zip"
        summary["archive_sha256"] = source_sha256
        return project, summary


def extract_factorytalk_zip(archive: zipfile.ZipFile, target: Path, *, limits: ImportLimits) -> dict[str, Any]:
    total_uncompressed = 0
    file_count = 0
    recognized_count = 0
    ignored_count = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        file_count += 1
        if file_count > limits.max_files:
            raise ValueError(f"FactoryTalk ZIP exceeds maximum file count of {limits.max_files}")
        if info.flag_bits & 0x1:
            raise ValueError(f"FactoryTalk ZIP contains encrypted member: {info.filename}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(f"FactoryTalk ZIP contains symlink member: {info.filename}")
        if info.file_size > limits.max_single_file_bytes:
            raise ValueError(f"FactoryTalk ZIP member is too large: {info.filename}")
        total_uncompressed += info.file_size
        if total_uncompressed > limits.max_total_uncompressed_bytes:
            raise ValueError("FactoryTalk ZIP exceeds maximum uncompressed size")
        member_path = safe_zip_member_path(info.filename)
        if member_path.suffix.lower() not in {".xml", ".par"}:
            ignored_count += 1
            continue
        destination = safe_destination(target, member_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, destination.open("wb") as output:
            output.write(source.read())
        recognized_count += 1
    return {
        "file_count": file_count,
        "recognized_file_count": recognized_count,
        "ignored_file_count": ignored_count,
        "uncompressed_bytes": total_uncompressed,
    }


def resolve_import_source_type(path: Path, source_type: str) -> str:
    normalized = source_type.lower()
    if normalized in {"plc_l5x", "plc_l5k", "factorytalk"}:
        return normalized
    if normalized == "plc":
        return plc_source_type_for_suffix(path)
    if normalized != "auto":
        raise ValueError(f"Unknown import source type: {source_type}")
    if path.suffix.lower() == ".zip" or path.is_dir() or path.suffix.lower() in {".xml", ".par"}:
        return "factorytalk"
    return plc_source_type_for_suffix(path)


def plc_source_type_for_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".l5x":
        return "plc_l5x"
    if suffix == ".l5k":
        return "plc_l5k"
    raise ValueError(f"Could not infer PLC import source type from: {path}")


def safe_zip_member_path(filename: str) -> PurePosixPath:
    normalized = filename.replace("\\", "/")
    if "\0" in normalized:
        raise ValueError("FactoryTalk ZIP contains a member with a NUL byte")
    path = PurePosixPath(normalized)
    if path.is_absolute():
        raise ValueError(f"FactoryTalk ZIP contains absolute path: {filename}")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"FactoryTalk ZIP contains unsafe path: {filename}")
    if parts[0].endswith(":"):
        raise ValueError(f"FactoryTalk ZIP contains Windows drive path: {filename}")
    return path


def safe_destination(root: Path, member_path: PurePosixPath) -> Path:
    destination = root.joinpath(*member_path.parts).resolve(strict=False)
    root_resolved = root.resolve(strict=True)
    if destination != root_resolved and root_resolved not in destination.parents:
        raise ValueError(f"FactoryTalk ZIP member escapes extraction root: {member_path}")
    return destination


def rewrite_factorytalk_project_paths(
    project: FactoryTalkProject,
    *,
    root: Path,
    source_name: str,
    source_sha256: str,
) -> FactoryTalkProject:
    screens = tuple(
        replace(screen, source_path=archive_member_path(source_name, root, Path(screen.source_path))) for screen in project.screens
    )
    parameter_files = tuple(
        replace(parameter_file, source_path=archive_member_path(source_name, root, Path(parameter_file.source_path)))
        for parameter_file in project.parameter_files
    )
    return replace(project, screens=screens, parameter_files=parameter_files, source_path=source_name, source_sha256=source_sha256)


def archive_member_path(source_name: str, root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return f"{source_name}:{path.name}"
    return f"{source_name}:{relative.as_posix()}"


def factorytalk_path_summary(path: Path) -> dict[str, Any]:
    if path.is_dir():
        recognized = [candidate for candidate in path.rglob("*") if candidate.is_file() and candidate.suffix.lower() in {".xml", ".par"}]
        return {
            "container": "directory",
            "recognized_file_count": len(recognized),
            "ignored_file_count": 0,
        }
    return {"container": "file", "recognized_file_count": 1, "ignored_file_count": 0}
