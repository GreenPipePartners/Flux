from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Thread
from time import monotonic
from typing import Any


REQUIRED_SUITE_FIELDS = {
    "name",
    "description",
    "command",
    "cwd",
    "required_env",
    "timeout_seconds",
    "external_services",
    "cleanup_expectations",
    "destructive_scope",
}


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Suite:
    name: str
    description: str
    command: tuple[str, ...]
    cwd: str
    required_env: tuple[str, ...]
    timeout_seconds: int
    external_services: tuple[str, ...]
    cleanup_expectations: str
    destructive_scope: str

    def missing_env(self, environ: dict[str, str] | None = None) -> tuple[str, ...]:
        source = os.environ if environ is None else environ
        return tuple(name for name in self.required_env if not source.get(name))

    def report(
        self,
        root: Path,
        environ: dict[str, str] | None = None,
        *,
        report_only: bool = True,
    ) -> dict[str, Any]:
        missing_env = self.missing_env(environ)
        return {
            **asdict(self),
            "command": list(self.command),
            "required_env": list(self.required_env),
            "external_services": list(self.external_services),
            "cwd_path": str((root / self.cwd).resolve()),
            "status": "blocked" if missing_env else "defined",
            "missing_env": list(missing_env),
            "report_only": report_only,
            "execution": {
                "status": "not_run" if report_only else "pending",
                "returncode": None,
                "duration_seconds": None,
                "output": "",
            },
        }


@dataclass(frozen=True)
class Manifest:
    name: str
    version: int
    description: str
    suites: tuple[Suite, ...]

    def suite_names(self) -> tuple[str, ...]:
        return tuple(suite.name for suite in self.suites)

    def select(self, names: list[str] | None = None) -> tuple[Suite, ...]:
        if not names:
            return self.suites
        by_name = {suite.name: suite for suite in self.suites}
        missing = [name for name in names if name not in by_name]
        if missing:
            raise ManifestError("Unknown suite(s): %s" % ", ".join(missing))
        return tuple(by_name[name] for name in names)


def load_manifest(path: Path) -> Manifest:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError("Could not read manifest %s: %s" % (path, exc)) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError("Invalid TOML in %s: %s" % (path, exc)) from exc
    return parse_manifest(data)


def parse_manifest(data: dict[str, Any]) -> Manifest:
    workspace = data.get("workspace")
    if not isinstance(workspace, dict):
        raise ManifestError("Manifest requires a [workspace] table")

    name = require_str(workspace, "name", "workspace")
    version = require_int(workspace, "version", "workspace", minimum=1)
    description = require_str(workspace, "description", "workspace")

    raw_suites = data.get("suite")
    if not isinstance(raw_suites, list) or not raw_suites:
        raise ManifestError("Manifest requires at least one [[suite]] entry")

    suites = tuple(parse_suite(raw_suite, index) for index, raw_suite in enumerate(raw_suites, start=1))
    names = [suite.name for suite in suites]
    duplicates = sorted({suite_name for suite_name in names if names.count(suite_name) > 1})
    if duplicates:
        raise ManifestError("Duplicate suite name(s): %s" % ", ".join(duplicates))
    return Manifest(name=name, version=version, description=description, suites=suites)


def parse_suite(raw_suite: Any, index: int) -> Suite:
    context = "suite #%s" % index
    if not isinstance(raw_suite, dict):
        raise ManifestError("%s must be a table" % context)

    missing = sorted(REQUIRED_SUITE_FIELDS - set(raw_suite))
    if missing:
        raise ManifestError("%s missing required field(s): %s" % (context, ", ".join(missing)))

    name = require_str(raw_suite, "name", context)
    return Suite(
        name=name,
        description=require_str(raw_suite, "description", name),
        command=require_str_tuple(raw_suite, "command", name, minimum=1),
        cwd=require_str(raw_suite, "cwd", name),
        required_env=require_str_tuple(raw_suite, "required_env", name),
        timeout_seconds=require_int(raw_suite, "timeout_seconds", name, minimum=1),
        external_services=require_str_tuple(raw_suite, "external_services", name),
        cleanup_expectations=require_str(raw_suite, "cleanup_expectations", name),
        destructive_scope=require_str(raw_suite, "destructive_scope", name),
    )


def require_str(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError("%s.%s must be a non-empty string" % (context, key))
    return value


def require_int(data: dict[str, Any], key: str, context: str, *, minimum: int) -> int:
    value = data.get(key)
    if not isinstance(value, int) or value < minimum:
        raise ManifestError("%s.%s must be an integer >= %s" % (context, key, minimum))
    return value


def require_str_tuple(
    data: dict[str, Any], key: str, context: str, *, minimum: int = 0
) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or len(value) < minimum:
        raise ManifestError("%s.%s must be a list with at least %s item(s)" % (context, key, minimum))
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ManifestError("%s.%s must contain only non-empty strings" % (context, key))
    return tuple(value)


def build_report(
    manifest: Manifest,
    suites: tuple[Suite, ...],
    root: Path,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    return {
        "workspace": {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
        },
        "report_only": not execute,
        "suite_count": len(suites),
        "suites": [suite.report(root, report_only=not execute) for suite in suites],
    }


def execute_report(report: dict[str, Any], *, stream: bool = True) -> bool:
    passed = True
    for suite in report["suites"]:
        execution = suite["execution"]
        if suite["missing_env"]:
            execution["status"] = "blocked"
            passed = False
            continue

        cwd_path = Path(suite["cwd_path"])
        if not cwd_path.is_dir():
            execution["status"] = "failed"
            execution["returncode"] = 127
            execution["output"] = "cwd does not exist: %s\n" % cwd_path
            passed = False
            if stream:
                print(execution["output"], end="", file=sys.stderr)
            continue

        if stream:
            print("\n[RUNNING] %s" % suite["name"])
            print("  cwd: %s" % cwd_path)
            print("  command: %s" % " ".join(suite["command"]))

        started = monotonic()
        output_lines: list[str] = []
        try:
            process = subprocess.Popen(
                suite["command"],
                cwd=str(cwd_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert process.stdout is not None

            def collect_output() -> None:
                for line in process.stdout:
                    output_lines.append(line)
                    if stream:
                        print(line, end="")

            reader = Thread(target=collect_output, daemon=True)
            reader.start()
            try:
                returncode = process.wait(timeout=suite["timeout_seconds"])
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = 124
                output_lines.append("Timed out after %ss\n" % suite["timeout_seconds"])
                if stream:
                    print(output_lines[-1], end="", file=sys.stderr)
            reader.join(timeout=1)
        except OSError as exc:
            returncode = 127
            output_lines.append("Could not execute command: %s\n" % exc)
            if stream:
                print(output_lines[-1], end="", file=sys.stderr)

        execution["returncode"] = returncode
        execution["duration_seconds"] = round(monotonic() - started, 3)
        execution["output"] = "".join(output_lines)
        if returncode == 0:
            execution["status"] = "passed"
            suite["status"] = "passed"
        else:
            execution["status"] = "failed"
            suite["status"] = "failed"
            passed = False
    return passed


def print_text_report(report: dict[str, Any]) -> None:
    workspace = report["workspace"]
    print("%s v%s" % (workspace["name"], workspace["version"]))
    print(workspace["description"])
    if report["report_only"]:
        print("Report-only: commands are described, not executed.")
    else:
        print("Execute mode: commands were executed where env gates allowed.")
    for suite in report["suites"]:
        print("")
        print("[%s] %s" % (suite["status"].upper(), suite["name"]))
        print("  %s" % suite["description"])
        print("  cwd: %s" % suite["cwd"])
        print("  command: %s" % " ".join(suite["command"]))
        print("  timeout: %ss" % suite["timeout_seconds"])
        print("  required env: %s" % (", ".join(suite["required_env"]) or "none"))
        if suite["missing_env"]:
            print("  missing env: %s" % ", ".join(suite["missing_env"]))
        if not report["report_only"]:
            execution = suite["execution"]
            print("  execution: %s" % execution["status"])
            if execution["returncode"] is not None:
                print("  returncode: %s" % execution["returncode"])
        print("  external services: %s" % (", ".join(suite["external_services"]) or "none"))
        print("  cleanup: %s" % suite["cleanup_expectations"])
        print("  destructive scope: %s" % suite["destructive_scope"])


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Report or execute Flux.test suite manifest definitions.")
    parser.add_argument("suite", nargs="*", help="Suite name(s) to report or execute. Defaults to all suites.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("manifest.toml"),
        help="Path to Flux.test manifest TOML.",
    )
    parser.add_argument("--execute", action="store_true", help="Execute selected suites. Default is report-only.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of text.")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        suites = manifest.select(args.suite)
    except ManifestError as exc:
        print("Flux.test manifest error: %s" % exc, file=sys.stderr)
        return 2

    report = build_report(manifest, suites, root, execute=args.execute)
    passed = True
    if args.execute:
        passed = execute_report(report, stream=not args.json)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
