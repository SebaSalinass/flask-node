"""Declarations and safe filesystem publication of installed package assets."""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .exceptions import AssetPublicationError, AssetResolutionError
from .package import validate_name


def relative_path(value: str | Path) -> str:
    text = str(value)
    path = Path(text)
    if (
        not text
        or "\x00" in text
        or path.is_absolute()
        or PureWindowsPath(text).drive
        or "\\" in text
        or ".." in path.parts
        or not path.parts
    ):
        raise AssetResolutionError(f"Unsafe asset path: {text!r}")
    return path.as_posix()


@dataclass(frozen=True)
class NodeAsset:
    package: str
    source: str
    destination: str

    def __post_init__(self):
        validate_name(self.package)
        object.__setattr__(self, "source", relative_path(self.source))
        object.__setattr__(self, "destination", relative_path(self.destination))


def destination_path(static: Path | None, destination: str) -> Path:
    if static is None:
        raise AssetPublicationError("No Flask static folder is configured.")
    root = static.resolve()
    target = root / destination
    for path in (*target.parents, target):
        if path == root:
            continue
        if path.is_relative_to(root) and path.is_symlink():
            raise AssetResolutionError(f"Symlink in static destination: {path}")
    resolved = target.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise AssetResolutionError(f"Destination escapes static folder: {destination}")
    return target


def validate_tree(path: Path) -> None:
    if path.is_symlink():
        raise AssetResolutionError(f"Symlink in published tree: {path}")
    if path.is_dir():
        for child in sorted(path.iterdir()):
            validate_tree(child)
    elif not path.is_file():
        raise AssetResolutionError(f"Unsupported asset file: {path}")


def publish(source: Path, target: Path) -> None:
    """Stage a copy, replace only its destination, and restore on rename failure."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".flask-node-", dir=target.parent) as temp:
        staged = Path(temp) / "asset"
        backup = Path(temp) / "previous"
        if source.is_dir():
            shutil.copytree(source, staged)
        else:
            shutil.copy2(source, staged)
        existed = target.exists()
        if existed:
            target.rename(backup)
        try:
            staged.rename(target)
        except OSError:
            if existed:
                backup.rename(target)
            raise
