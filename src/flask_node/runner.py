"""The single subprocess boundary for managed commands."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .exceptions import CommandExecutionError, ExecutableNotFoundError


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str | None = None
    stderr: str | None = None


class CommandRunner:
    def locate(self, executable: str) -> str | None:
        return shutil.which(executable)

    def run(
        self,
        executable: str,
        args: tuple[str, ...],
        *,
        cwd: Path,
        capture_output: bool = True,
    ) -> CommandResult:
        located = self.locate(executable)
        if located is None:
            raise ExecutableNotFoundError(
                f"Executable {executable!r} was not found. Install Node.js/npm or configure its path."
            )
        command = (located, *args)
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=False,
                check=False,
                text=True,
                capture_output=capture_output,
            )
        except FileNotFoundError as exc:
            raise ExecutableNotFoundError(
                f"Cannot launch {executable!r}: {exc}"
            ) from exc
        except OSError as exc:
            raise CommandExecutionError(str(exc), args=command, cwd=str(cwd)) from exc
        if result.returncode:
            detail = (result.stderr or result.stdout or "").strip()
            raise CommandExecutionError(
                f"{executable} exited with status {result.returncode}"
                + (f": {detail}" if detail else "."),
                args=command,
                cwd=str(cwd),
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return CommandResult(command, result.returncode, result.stdout, result.stderr)
