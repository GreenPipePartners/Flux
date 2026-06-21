#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / ".runtime" / "greenpipe-handoff"


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    version = args.version
    output = args.output.resolve()
    release_dir = output / "release" / "flux" / version
    docs_mount = output / "docs" / "flux" / version
    reset_dir(output)
    release_dir.mkdir(parents=True, exist_ok=True)
    docs_mount.mkdir(parents=True, exist_ok=True)

    commit = capture(["git", "rev-parse", "HEAD"]).strip()
    commit_ts = capture(["git", "show", "-s", "--format=%ct", "HEAD"]).strip()

    with tempfile.TemporaryDirectory(prefix="flux-release-") as temp_name:
        temp_dir = Path(temp_name)
        source_dir = temp_dir / ("flux-%s" % version)
        export_head(source_dir)
        overlay_submodules(source_dir, temp_dir)
        patch_site_url(source_dir / "mkdocs.yml", "https://greenpipe.partners/docs/flux/%s/" % version)

        source_archive = release_dir / ("flux-%s.tar.zst" % version)
        archive_directory(source_archive, source_dir.parent, source_dir.name, commit_ts)

        build_docs(source_dir, docs_mount)
        docs_stage = temp_dir / ("flux-docs-%s" % version)
        shutil.copytree(docs_mount, docs_stage)
        docs_archive = release_dir / ("flux-docs-%s.tar.zst" % version)
        archive_directory(docs_archive, docs_stage.parent, docs_stage.name, commit_ts)

        runner = release_dir / "flux-deploy.py"
        shutil.copy2(source_dir / "install" / "flux_deploy.py", runner)
        runner.chmod(0o755)

        checksums = {}
        for path in (source_archive, docs_archive, runner):
            checksums[path.name] = write_checksum(path)
            if args.sign:
                sign(path)

        write_manifest_examples(release_dir, version, checksums[source_archive.name], signed=args.sign)
        write_handoff_readme(output, version, commit, args.sign)

    print("Built GreenPipe handoff package at %s" % output)
    return 0


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Flux release artifacts for GreenPipe hosting.")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sign", action="store_true", help="Create detached GPG signatures with the default key.")
    return parser.parse_args(argv)


def run(command: list[str], *, cwd: Path = REPO_ROOT) -> None:
    print("+ %s" % " ".join(command))
    subprocess.run(command, cwd=str(cwd), check=True)


def capture(command: list[str], *, cwd: Path = REPO_ROOT) -> str:
    return subprocess.check_output(command, cwd=str(cwd), text=True)


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def export_head(destination: Path) -> None:
    destination.mkdir(parents=True)
    archive = destination.parent / "head.tar"
    run(["git", "archive", "--format=tar", "--output", str(archive), "HEAD"])
    run(["tar", "-xf", str(archive), "-C", str(destination)])


def overlay_submodules(destination: Path, temp_dir: Path) -> None:
    for path, commit in gitlinks():
        source = REPO_ROOT / path
        if not source.exists():
            raise SystemExit("submodule %s is missing; run git submodule update --init" % path)
        subprocess.run(["git", "-C", str(source), "cat-file", "-e", "%s^{commit}" % commit], check=True)
        target = destination / path
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.mkdir(parents=True)
        archive = temp_dir / (path.replace("/", "_") + ".tar")
        run(["git", "-C", str(source), "archive", "--format=tar", "--output", str(archive), commit])
        run(["tar", "-xf", str(archive), "-C", str(target)])


def gitlinks() -> list[tuple[str, str]]:
    links = []
    for line in capture(["git", "ls-tree", "HEAD"]).splitlines():
        metadata, path = line.split("\t", 1)
        mode, _kind, commit = metadata.split()
        if mode == "160000":
            links.append((path, commit))
    return links


def patch_site_url(config_path: Path, site_url: str) -> None:
    content = config_path.read_text(encoding="utf-8")
    lines = []
    replaced = False
    for line in content.splitlines():
        if line.startswith("site_url:"):
            lines.append("site_url: %s" % site_url)
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.insert(0, "site_url: %s" % site_url)
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def archive_directory(archive_path: Path, cwd: Path, directory_name: str, commit_ts: str) -> None:
    run(
        [
            "tar",
            "--sort=name",
            "--mtime=@%s" % commit_ts,
            "--owner=0",
            "--group=0",
            "--numeric-owner",
            "--zstd",
            "-cf",
            str(archive_path),
            directory_name,
        ],
        cwd=cwd,
    )


def build_docs(source_dir: Path, site_dir: Path) -> None:
    run(
        [
            "uv",
            "run",
            "--project",
            ".",
            "mkdocs",
            "build",
            "--strict",
            "--site-dir",
            str(site_dir),
        ],
        cwd=source_dir,
    )


def write_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text("%s  %s\n" % (value, path.name), encoding="utf-8")
    return value


def sign(path: Path) -> None:
    if not shutil.which("gpg"):
        raise SystemExit("gpg is required for --sign")
    run(["gpg", "--batch", "--yes", "--detach-sign", "--armor", "--output", str(path) + ".sig", str(path)])


def write_manifest_examples(release_dir: Path, version: str, source_sha256: str, *, signed: bool) -> None:
    release = {
        "version": version,
        "artifact_url": "https://greenpipe.partners/release/flux/%s/flux-%s.tar.zst" % (version, version),
        "sha256": source_sha256,
        "checksum_url": "https://greenpipe.partners/release/flux/%s/flux-%s.tar.zst.sha256" % (version, version),
    }
    if signed:
        release["signature_url"] = "https://greenpipe.partners/release/flux/%s/flux-%s.tar.zst.sig" % (version, version)
    manifest = {
        "apiVersion": "flux.greenpipe.partners/v1",
        "kind": "FluxInstall",
        "metadata": {"deployment_id": "dep_123", "site": "preview"},
        "spec": {
            "release": release,
            "target": {"allowed_hosts": "localhost,127.0.0.1", "web_bind": "0.0.0.0:8000"},
            "database": {"mode": "local"},
            "services": {"enable": True, "start": True, "web_workers": 8, "web_threads": 2},
        },
    }
    (release_dir / "manifest.example.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (release_dir / "manifest.example.yaml").write_text(manifest_yaml(version, source_sha256, signed=signed), encoding="utf-8")


def manifest_yaml(version: str, source_sha256: str, *, signed: bool) -> str:
    lines = [
        "apiVersion: flux.greenpipe.partners/v1",
        "kind: FluxInstall",
        "metadata:",
        "  deployment_id: dep_123",
        "  site: preview",
        "spec:",
        "  release:",
        "    version: %s" % version,
        "    artifact_url: https://greenpipe.partners/release/flux/%s/flux-%s.tar.zst" % (version, version),
        "    sha256: %s" % source_sha256,
        "    checksum_url: https://greenpipe.partners/release/flux/%s/flux-%s.tar.zst.sha256" % (version, version),
    ]
    if signed:
        lines.append("    signature_url: https://greenpipe.partners/release/flux/%s/flux-%s.tar.zst.sig" % (version, version))
    lines.extend(
        [
            "  target:",
            "    allowed_hosts: localhost,127.0.0.1",
            "    web_bind: 0.0.0.0:8000",
            "  database:",
            "    mode: local",
            "  services:",
            "    enable: true",
            "    start: true",
            "    web_workers: 8",
            "    web_threads: 2",
        ]
    )
    return "\n".join(lines) + "\n"


def write_handoff_readme(output: Path, version: str, commit: str, signed: bool) -> None:
    signature_note = "Detached .sig files were generated." if signed else "Detached .sig files were not generated; sign before production hosting."
    content = """# GreenPipe Flux {version} Handoff

Built from git commit `{commit}`.

Host these directories at `https://greenpipe.partners/`:

```text
release/flux/{version}/
docs/flux/{version}/
```

Expose this redirect:

```text
/docs/flux/latest/ -> /docs/flux/{version}/
```

{signature_note}
""".format(version=version, commit=commit, signature_note=signature_note)
    (output / "README.md").write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
