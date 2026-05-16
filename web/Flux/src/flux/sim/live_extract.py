from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LiveTagSpec:
    name: str
    data_type: str
    value: Any
    history_values: list[float]


@dataclass(frozen=True)
class LiveTagHistoryPoint:
    tag_name: str
    value: Any
    timestamp_ms: int
    quality: Any = 192


@dataclass(frozen=True)
class LiveTagExtraction:
    provider: str
    source_folder: str
    target_folder: str
    tag_configs: list[dict[str, Any]]
    history_points: list[LiveTagHistoryPoint]


@dataclass(frozen=True)
class DatasourceInfo:
    name: str
    db_type: str
    status: str
    payload: dict[str, Any]


DEFAULT_TRIAL_TAGS = [
    LiveTagSpec("Pressure", "Float4", 100.0, [101.0, 102.5, 104.0, 103.5]),
    LiveTagSpec("Rate", "Float4", 42.0, [40.0, 41.0, 43.5, 45.0]),
    LiveTagSpec("Cycles", "Int4", 7, [7, 8, 9, 10]),
]


def historical_path(*, provider: str, folder: str, tag_name: str, history_provider: str = "Core Historian") -> str:
    return f"histprov:{history_provider}:/sys:gateway:/prov:{provider}:/tag:{folder.strip('/')}/{tag_name}"


def datasource_info(fx, name: str) -> DatasourceInfo:
    payload = fx.db.get_connection_info(name)
    return DatasourceInfo(
        name=str(payload.get("Name") or payload.get("name") or name),
        db_type=normalize_db_type(payload.get("DBType") or payload.get("dbType") or payload.get("Driver") or ""),
        status=str(payload.get("Status") or payload.get("status") or ""),
        payload=payload,
    )


def normalize_db_type(value: Any) -> str:
    normalized = str(value or "").strip().upper().replace(" ", "_")
    aliases = {
        "POSTGRESQL": "POSTGRES",
        "POSTGRESQL": "POSTGRES",
        "PSQL": "POSTGRES",
        "MICROSOFT_SQL_SERVER": "MSSQL",
        "SQL_SERVER": "MSSQL",
        "MSSQLSERVER": "MSSQL",
    }
    return aliases.get(normalized, normalized)


def tag_path(*, provider: str, folder: str, tag_name: str | None = None) -> str:
    path = f"[{provider}]{folder.strip('/')}"
    return f"{path}/{tag_name}" if tag_name else path


def build_trial_live_source(
    fx,
    *,
    provider: str,
    source_folder: str,
    start_ms: int,
    sample_interval_ms: int = 60_000,
    tags: list[LiveTagSpec] | None = None,
    history_provider: str = "Core Historian",
) -> int:
    tags = tags or DEFAULT_TRIAL_TAGS
    fx.tag.configure(
        [
            {
                "name": source_folder,
                "tagType": "Folder",
                "tags": [memory_tag_config(tag) for tag in tags],
            }
        ],
        base_path=f"[{provider}]",
        collision_policy="o",
    )
    fx.tag.write_blocking(
        [tag_path(provider=provider, folder=source_folder, tag_name=tag.name) for tag in tags],
        [tag.value for tag in tags],
    )

    paths: list[str] = []
    values: list[Any] = []
    timestamps: list[int] = []
    qualities: list[int] = []
    for tag in tags:
        history_path = historical_path(
            provider=provider,
            folder=source_folder,
            tag_name=tag.name,
            history_provider=history_provider,
        )
        for index, value in enumerate(tag.history_values):
            paths.append(history_path)
            values.append(value)
            timestamps.append(start_ms + (index * sample_interval_ms))
            qualities.append(192)
    fx.historian.store_data_points(paths, values, timestamps=timestamps, qualities=qualities)
    return len(paths)


def extract_live_tags(
    fx,
    *,
    provider: str,
    source_folder: str,
    target_folder: str,
    start_ms: int,
    end_ms: int,
    history_provider: str = "Core Historian",
    return_size: int = 10_000,
) -> LiveTagExtraction:
    source_configs = fx.tag.get_configuration(tag_path(provider=provider, folder=source_folder), recursive=True)
    tag_configs = rename_root_folder(source_configs, source_folder=source_folder, target_folder=target_folder)
    tag_names = atomic_tag_names(tag_configs)
    history_paths = [
        historical_path(provider=provider, folder=source_folder, tag_name=name, history_provider=history_provider)
        for name in tag_names
    ]
    rows = fx.historian.query_raw_points(history_paths, start_ms, end_ms, return_size=return_size)
    points = rows_to_history_points(rows, tag_names=tag_names)
    return LiveTagExtraction(provider, source_folder, target_folder, tag_configs, points)


def replay_live_extraction(
    fx,
    extraction: LiveTagExtraction,
    *,
    history_provider: str = "Core Historian",
    collision_policy: str = "o",
) -> int:
    fx.tag.configure(extraction.tag_configs, base_path=f"[{extraction.provider}]", collision_policy=collision_policy)
    if not extraction.history_points:
        return 0
    paths = [
        historical_path(
            provider=extraction.provider,
            folder=extraction.target_folder,
            tag_name=point.tag_name,
            history_provider=history_provider,
        )
        for point in extraction.history_points
    ]
    values = [point.value for point in extraction.history_points]
    timestamps = [point.timestamp_ms for point in extraction.history_points]
    qualities = [point.quality for point in extraction.history_points]
    fx.historian.store_data_points(paths, values, timestamps=timestamps, qualities=qualities)
    return len(paths)


def cleanup_live_extraction_trial(
    fx,
    *,
    provider: str,
    source_folder: str,
    target_folder: str,
    tag_names: list[str],
    history_provider: str = "Core Historian",
) -> None:
    for folder in [source_folder, target_folder]:
        try:
            fx.tag.delete_tags(tag_path(provider=provider, folder=folder))
        except Exception:
            pass


def trial_tag_paths(*, provider: str, folders: list[str], tag_names: list[str]) -> list[str]:
    return [tag_path(provider=provider, folder=folder, tag_name=name) for folder in folders for name in tag_names]


def trial_history_paths(
    *, provider: str, folders: list[str], tag_names: list[str], history_provider: str = "Core Historian"
) -> list[str]:
    return [
        historical_path(provider=provider, folder=folder, tag_name=name, history_provider=history_provider)
        for folder in folders
        for name in tag_names
    ]


def memory_tag_config(tag: LiveTagSpec) -> dict[str, Any]:
    return {
        "name": tag.name,
        "tagType": "AtomicTag",
        "valueSource": "memory",
        "dataType": tag.data_type,
        "value": tag.value,
    }


def rename_root_folder(configs: list[dict[str, Any]], *, source_folder: str, target_folder: str) -> list[dict[str, Any]]:
    renamed = [dict(config) for config in configs]
    if len(renamed) == 1 and renamed[0].get("name") == source_folder:
        renamed[0]["name"] = target_folder
        return renamed
    return [{"name": target_folder, "tagType": "Folder", "tags": renamed}]


def atomic_tag_names(configs: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []

    def visit(config: dict[str, Any]):
        if config.get("tagType") == "AtomicTag" and config.get("name"):
            names.append(str(config["name"]))
        for child in config.get("tags") or []:
            if isinstance(child, dict):
                visit(child)

    for config in configs:
        visit(config)
    return names


def rows_to_history_points(rows, *, tag_names: list[str]) -> list[LiveTagHistoryPoint]:
    points: list[LiveTagHistoryPoint] = []
    for row in rows:
        tag_name = tag_name_from_history_row(row, tag_names=tag_names)
        if not tag_name:
            continue
        timestamp = row.get("timestamp", row.get("t_stamp", row.get("time")))
        if timestamp is None:
            continue
        points.append(
            LiveTagHistoryPoint(
                tag_name=tag_name,
                value=row.get("value"),
                timestamp_ms=int(timestamp),
                quality=row.get("quality", 192),
            )
        )
    return points


def tag_name_from_history_row(row: dict[str, Any], *, tag_names: list[str]) -> str | None:
    raw_path = str(row.get("path") or row.get("tagPath") or row.get("tag_path") or "")
    if raw_path.startswith("value_"):
        try:
            index = int(raw_path.split("_", 1)[1])
        except ValueError:
            index = -1
        if 0 <= index < len(tag_names):
            return tag_names[index]
    for name in tag_names:
        if raw_path == name or raw_path.endswith("/" + name) or raw_path.endswith("_" + name):
            return name
    return tag_names[0] if len(tag_names) == 1 else None
