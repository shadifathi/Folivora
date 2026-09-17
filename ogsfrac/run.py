"""Run OGS and surface failures as exceptions rather than printed text."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class OGSError(RuntimeError):
    pass


@dataclass
class OGSResult:
    returncode: int
    stdout: str
    stderr: str
    output_dir: Path

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class OGSSimulation:
    """Thin wrapper over the ogs binary.

    Difference from the notebook version: a non-zero exit raises instead of
    printing, so a failed run in a loop or script cannot be mistaken for a
    successful one.
    """

    def __init__(self, project_file, ogs_executable="ogs", output_dir=None, check=True):
        self.project_file = Path(project_file)
        self.ogs_executable = ogs_executable
        self.output_dir = Path(output_dir) if output_dir else self.project_file.parent
        self.check = check

    def run(self, extra_args=(), log_file=None, verbose=True) -> OGSResult:
        if not self.project_file.exists():
            raise FileNotFoundError(self.project_file)
        if shutil.which(self.ogs_executable) is None and not Path(self.ogs_executable).exists():
            raise FileNotFoundError(
                f"OGS executable '{self.ogs_executable}' not found on PATH. "
                f"Pass ogs_executable='/path/to/ogs'."
            )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [self.ogs_executable, str(self.project_file), "-o", str(self.output_dir), *extra_args]
        if verbose:
            print("$", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        result = OGSResult(proc.returncode, proc.stdout, proc.stderr, self.output_dir)
        if log_file:
            Path(log_file).write_text(proc.stdout + "\n" + proc.stderr)
        if self.check and not result.ok:
            tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-25:])
            raise OGSError(f"OGS exited {proc.returncode} for {self.project_file.name}:\n{tail}")
        return result
