"""Resolve installed entries using Node, without loading package code."""

import json
from pathlib import Path, PureWindowsPath

from .exceptions import EntryResolutionError
from .runner import CommandRunner

# Only built-in modules are loaded. The synthetic anchor need not exist.
_SCRIPT = """
const { createRequire, isBuiltin } = require('node:module');
const [anchor, specifier] = process.argv.slice(1);
try {
    if (isBuiltin(specifier)) {
        throw Object.assign(new Error('Built-in modules are unsupported'), {
            code: 'ERR_UNSUPPORTED_BUILTIN'
        });
    }
    const resolved = createRequire(anchor).resolve(specifier);
    process.stdout.write(JSON.stringify({path: resolved}));
} catch (error) {
    process.stdout.write(JSON.stringify({error: {
        code: error.code || 'ERR_ENTRY_RESOLUTION', message: error.message
    }}));
}
"""


def validate_subpath(subpath: str | None) -> str | None:
    if subpath is None:
        return None
    if (
        not isinstance(subpath, str)
        or not subpath
        or Path(subpath).is_absolute()
        or PureWindowsPath(subpath).drive
        or "\\" in subpath
        or "\x00" in subpath
        or "%" in subpath
        or any(part in ("", ".", "..") for part in subpath.split("/"))
    ):
        raise EntryResolutionError(f"Unsafe package entry subpath: {subpath!r}")
    return subpath


def resolve_entry(
    runner: CommandRunner,
    node_bin: str,
    directory: Path,
    root: Path,
    specifier: str,
) -> Path:
    result = runner.run(
        node_bin,
        (
            "--input-type=commonjs",
            "--eval",
            _SCRIPT,
            "--",
            str(directory / ".flask-node-resolver.cjs"),
            specifier,
        ),
        cwd=directory,
        capture_output=True,
    )
    try:
        payload = json.loads(result.stdout or "")
        if not isinstance(payload, dict):
            raise TypeError("expected an object")
        if "error" in payload:
            error = payload["error"]
            if not isinstance(error, dict):
                raise ValueError("invalid error response")
            detail = (
                f"Cannot resolve entry {specifier!r}: "
                f"{error.get('code', 'ERR_ENTRY_RESOLUTION')}: "
                f"{error.get('message', 'unknown resolution failure')}"
            )
            if result.stderr:
                detail += f"; stderr={result.stderr!r}"
            raise EntryResolutionError(detail)
        value = payload.get("path")
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError(
                "expected an absolute file path; built-ins are unsupported"
            )
        target = Path(value).resolve(strict=True)
        if not target.is_relative_to(root):
            raise EntryResolutionError(
                f"Entry {specifier!r} escapes its installed package: {target}"
            )
        if not target.is_file():
            raise EntryResolutionError(
                f"Entry {specifier!r} is not a regular file: {target}"
            )
        return target
    except (ValueError, OSError, RuntimeError, TypeError) as exc:
        raise EntryResolutionError(
            f"Cannot resolve entry {specifier!r}: {exc}; "
            f"stdout={result.stdout!r}; stderr={result.stderr!r}"
        ) from exc
