"""Safe access to installed package files, without asset delivery."""

import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .exceptions import AssetResolutionError, ConfigurationError

_NAME = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*\Z")


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ConfigurationError(f"Invalid registry package name: {name!r}")
    return name


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    root: Path

    def resolve(self, asset: str | Path) -> Path:
        value = str(asset)
        relative = Path(value)
        if (
            relative.is_absolute()
            or PureWindowsPath(value).drive
            or "\\" in value
            or ".." in relative.parts
        ):
            raise AssetResolutionError(f"Unsafe asset path: {value!r}")
        try:
            target = (self.root / relative).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise AssetResolutionError(
                f"Asset {value!r} is unavailable in {self.name}"
            ) from exc
        if not target.is_relative_to(self.root):
            raise AssetResolutionError(f"Asset escapes package {self.name}: {value!r}")
        return target
