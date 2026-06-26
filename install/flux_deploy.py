#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


USER_AGENT = "flux-deploy/0.1.0"
DEFAULT_WORK_DIR = Path("/var/tmp/flux-deploy")


class DeployError(RuntimeError):
    pass


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "apply":
            return apply(args)
        if args.command == "plan":
            return plan(args)
    except DeployError as exc:
        emit(args, "deploy", "error", str(exc))
        return 1
    raise AssertionError("unhandled command")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a typed Flux deployment manifest.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name in ("apply", "plan"):
        command = subparsers.add_parser(command_name)
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument("--manifest-url", help="HTTPS URL returning a FluxInstall JSON manifest.")
        source.add_argument("--manifest", help="Local FluxInstall JSON manifest path.")
        command.add_argument("--claim-token", default="", help="One-time deployment claim token.")
        command.add_argument("--events-url", default="", help="Override deployment event callback URL.")
        command.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
        command.add_argument("--json", action="store_true", help="Emit JSON-lines status events.")

    apply_parser = subparsers.choices["apply"]
    apply_parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run to the installer.")
    apply_parser.add_argument("--skip-signature", action="store_true", help="Skip detached signature verification.")
    apply_parser.add_argument("--artifact", type=Path, help="Use a local artifact instead of downloading artifact_url.")
    return parser.parse_args(argv)


def plan(args: argparse.Namespace) -> int:
    manifest = load_manifest(args)
    installer_args = build_installer_args(manifest, dry_run=True)
    payload = {
        "manifest": manifest.get("metadata", {}),
        "artifact_url": manifest["spec"]["release"].get("artifact_url", ""),
        "installer_args": installer_args,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def apply(args: argparse.Namespace) -> int:
    manifest = load_manifest(args)
    release = manifest["spec"]["release"]
    metadata = manifest.get("metadata", {})
    deployment_id = metadata.get("deployment_id", "manual")
    args.deployment_id = deployment_id
    if not args.events_url:
        args.events_url = manifest.get("spec", {}).get("reporting", {}).get("events_url", "")
    version = release["version"]
    run_dir = args.work_dir / safe_name(str(deployment_id))
    download_dir = run_dir / "download"
    unpack_dir = run_dir / "unpack"
    download_dir.mkdir(parents=True, exist_ok=True)

    emit(args, "manifest", "ok", "loaded FluxInstall manifest")
    sudo_command = None
    if args.dry_run:
        emit(args, "preflight", "ok", "dry-run selected; host mutations limited to installer dry-run")
    else:
        sudo_command = ensure_unpack_tools(args)

    artifact = args.artifact or download_artifact(args, release, download_dir)
    verify_sha256(artifact, release["sha256"])
    emit(args, "artifact", "ok", "verified artifact checksum")

    if not args.skip_signature and release.get("signature_url"):
        verify_signature(args, release, artifact, download_dir)

    reset_dir(unpack_dir)
    unpack_artifact(args, artifact, unpack_dir)
    source_dir = find_source_dir(unpack_dir, version)
    emit(args, "unpack", "ok", "unpacked release artifact to %s" % source_dir)

    command = build_installer_args(manifest, dry_run=args.dry_run)
    emit(args, "installer", "running", "running native installer")
    run_native_installer(
        args,
        command,
        cwd=source_dir,
        dry_run=args.dry_run,
        sudo_command=sudo_command,
    )
    emit(args, "installer", "ok", "native installer completed")
    return 0


def load_manifest(args: argparse.Namespace) -> Dict[str, Any]:
    if args.manifest_url:
        raw = read_url(args.manifest_url, args.claim_token)
    else:
        raw = Path(args.manifest).read_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DeployError("Flux deploy manifests must be JSON for the standalone runner: %s" % exc)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Dict[str, Any]) -> None:
    if manifest.get("apiVersion") != "flux.greenpipe.partners/v1":
        raise DeployError("unsupported apiVersion")
    if manifest.get("kind") != "FluxInstall":
        raise DeployError("unsupported manifest kind")
    spec = required_dict(manifest, "spec")
    release = required_dict(spec, "release")
    for key in ("version", "artifact_url", "sha256"):
        if not release.get(key):
            raise DeployError("manifest spec.release.%s is required" % key)


def required_dict(value: Dict[str, Any], key: str) -> Dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise DeployError("manifest %s must be an object" % key)
    return child


def read_url(url: str, token: str) -> bytes:
    request = urllib.request.Request(url, headers=request_headers(token))
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise DeployError("failed to fetch %s: %s" % (url, exc))


def request_headers(token: str) -> Dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = "Bearer %s" % token
        headers["X-Flux-Claim-Token"] = token
    return headers


def download_artifact(args: argparse.Namespace, release: Dict[str, Any], download_dir: Path) -> Path:
    url = release["artifact_url"]
    filename = Path(urllib.parse.urlparse(url).path).name
    if not filename:
        raise DeployError("artifact_url must end with a filename")
    target = download_dir / filename
    emit(args, "artifact", "running", "downloading %s" % url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as file_obj:
            shutil.copyfileobj(response, file_obj)
    except urllib.error.URLError as exc:
        raise DeployError("failed to download artifact: %s" % exc)
    return target


def verify_sha256(path: Path, expected: str) -> None:
    normalized = expected.strip().lower()
    if len(normalized) != 64:
        raise DeployError("manifest sha256 must be a 64-character hex digest")
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != normalized:
        raise DeployError("artifact checksum mismatch: expected %s got %s" % (normalized, actual))


def verify_signature(args: argparse.Namespace, release: Dict[str, Any], artifact: Path, download_dir: Path) -> None:
    if not shutil.which("gpg"):
        raise DeployError("gpg is required for signature verification; use --skip-signature only for preview installs")
    signature_url = release["signature_url"]
    signature = download_dir / Path(urllib.parse.urlparse(signature_url).path).name
    emit(args, "signature", "running", "downloading %s" % signature_url)
    request = urllib.request.Request(signature_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, signature.open("wb") as file_obj:
            shutil.copyfileobj(response, file_obj)
    except urllib.error.URLError as exc:
        raise DeployError("failed to download signature: %s" % exc)
    subprocess.run(["gpg", "--verify", str(signature), str(artifact)], check=True)
    emit(args, "signature", "ok", "verified release signature")


def ensure_unpack_tools(args: argparse.Namespace) -> Optional[str]:
    if shutil.which("tar") and shutil.which("zstd"):
        return None
    sudo_command = None
    if needs_elevation(dry_run=False):
        sudo_command = request_sudo(args)
    distro = detect_distro_family()
    emit(args, "bootstrap-packages", "running", "installing tar/zstd bootstrap dependencies")
    if distro == "apt":
        run_privileged_subprocess(["apt-get", "update"], sudo_command=sudo_command)
        run_privileged_subprocess(
            ["apt-get", "install", "-y", "tar", "zstd", "ca-certificates"],
            sudo_command=sudo_command,
        )
    elif distro == "dnf":
        manager = shutil.which("dnf") or shutil.which("yum") or "dnf"
        run_privileged_subprocess(
            [manager, "install", "-y", "tar", "zstd", "ca-certificates"],
            sudo_command=sudo_command,
        )
    else:
        raise DeployError("unsupported distro for bootstrap dependency install")
    return sudo_command


def needs_elevation(*, dry_run: bool) -> bool:
    return not dry_run and hasattr(os, "geteuid") and os.geteuid() != 0


def request_sudo(args: argparse.Namespace) -> str:
    sudo_command = shutil.which("sudo")
    if not sudo_command:
        raise DeployError("Flux install requires root but sudo is not installed; re-run with sudo")
    emit(args, "elevation", "running", "Flux install requires root; requesting sudo credentials")
    try:
        run_subprocess([sudo_command, "-v"])
    except DeployError as exc:
        raise DeployError("sudo elevation failed; re-run with sudo or fix sudo access") from exc
    emit(args, "elevation", "ok", "sudo credentials accepted")
    return sudo_command


def run_privileged_subprocess(command: list[str], *, sudo_command: Optional[str]) -> None:
    run_subprocess(privileged_command(command, sudo_command=sudo_command))


def run_native_installer(
    args: argparse.Namespace,
    command: list[str],
    *,
    cwd: Path,
    dry_run: bool,
    sudo_command: Optional[str] = None,
) -> None:
    if needs_elevation(dry_run=dry_run):
        sudo_command = sudo_command or request_sudo(args)
    run_subprocess(privileged_command(command, sudo_command=sudo_command), cwd=cwd)


def privileged_command(command: list[str], *, sudo_command: Optional[str]) -> list[str]:
    if not sudo_command:
        return command
    return [sudo_command, *command]


def run_subprocess(command: list[str], *, cwd: Optional[Path] = None) -> None:
    try:
        subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)
    except subprocess.CalledProcessError as exc:
        raise DeployError("command failed with exit code %s: %s" % (exc.returncode, command)) from exc


def detect_distro_family() -> str:
    os_release = Path("/etc/os-release")
    data: Dict[str, str] = {}
    if os_release.exists():
        for line in os_release.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            data[key] = value.strip().strip('"').lower()
    ids = {data.get("ID", ""), *data.get("ID_LIKE", "").split()}
    if ids & {"ubuntu", "debian"}:
        return "apt"
    if ids & {"rhel", "fedora", "centos", "rocky", "almalinux"}:
        return "dnf"
    return "unknown"


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def unpack_artifact(args: argparse.Namespace, artifact: Path, unpack_dir: Path) -> None:
    emit(args, "unpack", "running", "extracting %s" % artifact.name)
    subprocess.run(["tar", "--zstd", "-xf", str(artifact), "-C", str(unpack_dir)], check=True)


def find_source_dir(unpack_dir: Path, version: str) -> Path:
    expected = unpack_dir / ("flux-%s" % version)
    if expected.exists():
        return expected
    dirs = [path for path in unpack_dir.iterdir() if path.is_dir()]
    if len(dirs) == 1:
        return dirs[0]
    raise DeployError("artifact must unpack to one source directory")


def build_installer_args(manifest: Dict[str, Any], *, dry_run: bool) -> list[str]:
    spec = manifest["spec"]
    target = spec.get("target", {})
    database = spec.get("database", {})
    services = spec.get("services", {})
    command = ["python3", "install/flux_installer.py"]
    if dry_run:
        command.append("--dry-run")
    if services.get("start"):
        command.append("--start")
    if services.get("enable") is False:
        command.append("--no-enable")
    add_option(command, "--allowed-hosts", target.get("allowed_hosts"))
    add_option(command, "--csrf-trusted-origins", target.get("csrf_trusted_origins"))
    add_option(command, "--web-bind", target.get("web_bind"))
    add_option(command, "--web-workers", services.get("web_workers"))
    add_option(command, "--web-threads", services.get("web_threads"))
    add_option(command, "--field-agent-base-port", services.get("field_agent_base_port"))
    if database.get("mode") == "external":
        database_url = database.get("database_url") or os.environ.get(database.get("database_url_env", "FLUX_DATABASE_URL"))
        if not database_url:
            raise DeployError("external database mode requires database_url or FLUX_DATABASE_URL")
        command.extend(["--database-url", str(database_url), "--skip-postgres-setup"])
    return command


def add_option(command: list[str], flag: str, value: Any) -> None:
    if value is None or value == "":
        return
    command.extend([flag, str(value)])


def emit(args: argparse.Namespace, stage: str, state: str, message: str) -> None:
    payload = {
        "deployment_id": getattr(args, "deployment_id", ""),
        "stage": stage,
        "state": state,
        "message": message,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, sort_keys=True), flush=True)
    else:
        print("[%s] %s: %s" % (state.upper(), stage, message), flush=True)
    post_event(args, payload)


def post_event(args: argparse.Namespace, payload: Dict[str, Any]) -> None:
    events_url = getattr(args, "events_url", "")
    if not events_url:
        return
    data = json.dumps(payload).encode("utf-8")
    headers = request_headers(getattr(args, "claim_token", ""))
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(events_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10):
            return
    except urllib.error.URLError:
        return


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value) or "manual"


if __name__ == "__main__":
    raise SystemExit(main())
