from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


OPENPLC_ROOT_ENV = "FLUX_DEEP_OPENPLC_ROOT"


@dataclass(frozen=True)
class OpenPlcCompileResult:
    source_path: Path
    work_dir: Path
    generated_files: tuple[Path, ...]
    stdout: str
    stderr: str


@dataclass(frozen=True)
class OpenPlcHarnessResult:
    binary_path: Path
    stdout: str
    stderr: str


@dataclass(frozen=True)
class OpenPlcV3Toolchain:
    root: Path

    @classmethod
    def from_env(cls) -> "OpenPlcV3Toolchain | None":
        value = os.environ.get(OPENPLC_ROOT_ENV, "").strip()
        if not value:
            return None
        toolchain = cls(Path(value))
        return toolchain if toolchain.is_available() else None

    @property
    def webserver_dir(self) -> Path:
        return self.root / "webserver"

    @property
    def library_dir(self) -> Path:
        return self.webserver_dir / "lib"

    @property
    def compiler_path(self) -> Path:
        webserver_compiler = self.webserver_dir / "iec2c"
        if webserver_compiler.exists():
            return webserver_compiler
        return self.root / "utils" / "matiec_src" / "iec2c"

    def is_available(self) -> bool:
        return self.compiler_path.exists() and (self.library_dir / "ieclib.txt").exists()

    def compile_st(
        self,
        source_path: str | Path,
        *,
        output_dir: str | Path | None = None,
        timeout_seconds: int = 30,
    ) -> OpenPlcCompileResult:
        if not self.is_available():
            raise FileNotFoundError(
                "OpenPLC v3 toolchain is unavailable. Set FLUX_DEEP_OPENPLC_ROOT to a "
                "checkout with utils/matiec_src/iec2c built."
            )

        source = Path(source_path)
        if output_dir is None:
            work_dir = Path(tempfile.mkdtemp(prefix="flux-deep-openplc-"))
        else:
            work_dir = Path(output_dir)
            work_dir.mkdir(parents=True, exist_ok=True)

        compile_source = work_dir / source.name
        shutil.copy2(source, compile_source)
        library_link = work_dir / "lib"
        if not library_link.exists():
            library_link.symlink_to(self.library_dir, target_is_directory=True)

        process = subprocess.run(
            [str(self.compiler_path), "-f", "-l", "-p", "-r", "-R", "-a", str(compile_source)],
            cwd=work_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if process.returncode != 0:
            raise RuntimeError(
                "OpenPLC v3 compiler failed with exit code %(code)s\nSTDOUT:\n%(stdout)s\nSTDERR:\n%(stderr)s"
                % {"code": process.returncode, "stdout": process.stdout, "stderr": process.stderr}
            )

        generated = tuple(
            path
            for path in (work_dir / name for name in OPENPLC_GENERATED_FILES)
            if path.exists()
        )
        return OpenPlcCompileResult(
            source_path=compile_source,
            work_dir=work_dir,
            generated_files=generated,
            stdout=process.stdout,
            stderr=process.stderr,
        )

    def compile_and_run_harness(
        self,
        compiled: OpenPlcCompileResult,
        harness_source: str,
        *,
        timeout_seconds: int = 30,
    ) -> OpenPlcHarnessResult:
        harness_path = compiled.work_dir / "flux_deep_harness.cpp"
        binary_path = compiled.work_dir / "flux_deep_harness"
        harness_path.write_text(harness_source, encoding="utf-8")

        compile_process = subprocess.run(
            [
                "g++",
                "-std=gnu++11",
                str(harness_path),
                str(compiled.work_dir / "Config0.c"),
                str(compiled.work_dir / "Res0.c"),
                "-I",
                str(compiled.work_dir),
                "-I",
                str(self.root / "webserver" / "core" / "lib"),
                "-o",
                str(binary_path),
            ],
            cwd=compiled.work_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if compile_process.returncode != 0:
            raise RuntimeError(
                "OpenPLC harness compilation failed with exit code %(code)s\nSTDOUT:\n%(stdout)s\nSTDERR:\n%(stderr)s"
                % {
                    "code": compile_process.returncode,
                    "stdout": compile_process.stdout,
                    "stderr": compile_process.stderr,
                }
            )

        run_process = subprocess.run(
            [str(binary_path)],
            cwd=compiled.work_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if run_process.returncode != 0:
            raise RuntimeError(
                "OpenPLC harness run failed with exit code %(code)s\nSTDOUT:\n%(stdout)s\nSTDERR:\n%(stderr)s"
                % {"code": run_process.returncode, "stdout": run_process.stdout, "stderr": run_process.stderr}
            )

        return OpenPlcHarnessResult(
            binary_path=binary_path,
            stdout=run_process.stdout,
            stderr=run_process.stderr,
        )


OPENPLC_GENERATED_FILES = (
    "POUS.c",
    "POUS.h",
    "LOCATED_VARIABLES.h",
    "VARIABLES.csv",
    "Config0.c",
    "Config0.h",
    "Res0.c",
)
