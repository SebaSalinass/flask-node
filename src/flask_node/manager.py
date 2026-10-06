"""Application-local Node project lifecycle and dependency operations."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import (
    AssetResolutionError,
    ConfigurationError,
    DependencyConflictError,
    EnvironmentError,
    PackageNotFoundError,
)
from .package import Package, validate_name
from .runner import CommandResult, CommandRunner


@dataclass(frozen=True)
class Dependency:
    version: str
    dev: bool = False


class NodeManager:
    def __init__(
        self,
        directory: Path,
        *,
        node_bin: str = "node",
        npm_bin: str = "npm",
        npx_bin: str = "npx",
        runner: CommandRunner | None = None,
    ):
        self.directory = directory.resolve()
        self.node_bin, self.npm_bin, self.npx_bin = node_bin, npm_bin, npx_bin
        self.runner = runner if runner is not None else CommandRunner()
        self._requirements: dict[str, Dependency] = {}

    @property
    def manifest_path(self) -> Path:
        return self.directory / "package.json"

    def _read_manifest(self) -> dict[str, Any]:
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise TypeError("manifest must be an object")
            for section in ("dependencies", "devDependencies"):
                dependencies = data.get(section, {})
                if not isinstance(dependencies, dict) or not all(
                    isinstance(k, str) and isinstance(v, str)
                    for k, v in dependencies.items()
                ):
                    raise ValueError(f"{section} must map package names to strings")
            return data
        except (OSError, ValueError, TypeError) as exc:
            raise EnvironmentError(f"Cannot read {self.manifest_path}: {exc}") from exc

    def _write_manifest(self, data: dict[str, Any]) -> None:
        try:
            self.manifest_path.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            raise EnvironmentError(f"Cannot write {self.manifest_path}: {exc}") from exc

    def initialize(self) -> Path:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            # Exclusive creation preserves existing manifests, including concurrent init.
            with self.manifest_path.open("x", encoding="utf-8") as stream:
                json.dump(
                    {"private": True, "dependencies": {}, "devDependencies": {}},
                    stream,
                    indent=2,
                )
                stream.write("\n")
        except FileExistsError:
            self._read_manifest()
        except OSError as exc:
            raise EnvironmentError(
                f"Cannot initialize {self.directory}: {exc}"
            ) from exc
        return self.directory

    def require(self, name: str, version: str = "*", *, dev: bool = False) -> None:
        validate_name(name)
        self._validate_version(version)
        dependency = Dependency(version, dev)
        previous = self._requirements.get(name)
        if previous is not None and previous != dependency:
            raise DependencyConflictError(
                f"Conflicting requirements for {name}: {previous} and {dependency}"
            )
        self._requirements[name] = dependency

    @staticmethod
    def _validate_version(version: str) -> None:
        if not isinstance(version, str) or not version.strip() or "\x00" in version:
            raise ConfigurationError("A dependency version must be a nonempty string.")

    def _merge_requirements(self, data: dict[str, Any]) -> dict[str, Any]:
        for name, dependency in self._requirements.items():
            section = "devDependencies" if dependency.dev else "dependencies"
            other = "dependencies" if dependency.dev else "devDependencies"
            data.setdefault(other, {}).pop(name, None)
            data.setdefault(section, {})[name] = dependency.version
        return data

    def install(
        self,
        name: str | None = None,
        version: str | None = None,
        *,
        dev: bool = False,
        capture_output: bool = True,
    ) -> CommandResult:
        if name is None and (version is not None or dev):
            raise ConfigurationError("version/dev require a package name.")
        if name is not None:
            validate_name(name)
            if version is not None:
                self._validate_version(version)
            required = self._requirements.get(name)
            if required and (
                required.dev != dev
                or (version is not None and version != required.version)
            ):
                raise DependencyConflictError(
                    f"Installation contradicts the declared requirement for {name}."
                )
            if required:
                version = required.version
        self.initialize()
        self._write_manifest(self._merge_requirements(self._read_manifest()))
        args = ["install"]
        if name is not None:
            args.extend(
                [
                    "--save-dev" if dev else "--save-prod",
                    "--",
                    name + (f"@{version}" if version is not None else ""),
                ]
            )
        return self.npm(*args, capture_output=capture_output)

    def uninstall(self, name: str, *, capture_output: bool = True) -> CommandResult:
        validate_name(name)
        if name in self._requirements:
            raise DependencyConflictError(
                f"Cannot uninstall actively required package {name}."
            )
        return self.npm("uninstall", "--", name, capture_output=capture_output)

    def _check_environment(self) -> None:
        if not self.manifest_path.is_file():
            raise EnvironmentError(
                "Node environment is not initialized. Run 'flask node init'."
            )
        self._read_manifest()

    def npm(self, *args: str, capture_output: bool = True) -> CommandResult:
        self._check_environment()
        return self.runner.run(
            self.npm_bin, args, cwd=self.directory, capture_output=capture_output
        )

    def npx(self, *args: str, capture_output: bool = True) -> CommandResult:
        self._check_environment()
        return self.runner.run(
            self.npx_bin, args, cwd=self.directory, capture_output=capture_output
        )

    def ci(self, *, capture_output: bool = True) -> CommandResult:
        self._check_environment()
        if not (self.directory / "package-lock.json").is_file():
            raise EnvironmentError(
                "npm ci requires package-lock.json. Run 'flask node install' first."
            )
        data = self._read_manifest()
        for name, dependency in self._requirements.items():
            section = "devDependencies" if dependency.dev else "dependencies"
            other = "dependencies" if dependency.dev else "devDependencies"
            if data.get(section, {}).get(
                name
            ) != dependency.version or name in data.get(other, {}):
                raise DependencyConflictError(
                    f"Manifest disagrees with the declared requirement for {name}."
                )
        return self.npm("ci", capture_output=capture_output)

    def package(self, name: str) -> Package:
        validate_name(name)
        modules = (self.directory / "node_modules").resolve()
        root = (modules / name).resolve()
        if not modules.is_relative_to(self.directory) or not root.is_relative_to(
            modules
        ):
            raise AssetResolutionError(
                f"Package {name} escapes the managed environment."
            )
        try:
            manifest = (root / "package.json").resolve()
            if not manifest.is_relative_to(root):
                raise AssetResolutionError(f"Package manifest escapes {name}.")
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("version"), str):
                raise TypeError("missing package version")
        except (OSError, TypeError) as exc:
            raise PackageNotFoundError(
                f"Package {name!r} is not installed or has an invalid manifest."
            ) from exc
        return Package(name, data["version"], root)

    def resolve(self, name: str, asset: str | Path) -> Path:
        return self.package(name).resolve(asset)

    def status(self) -> dict[str, Any]:
        return {
            "directory": str(self.directory),
            "initialized": self.manifest_path.is_file(),
            "node": self.runner.locate(self.node_bin),
            "npm": self.runner.locate(self.npm_bin),
            "npx": self.runner.locate(self.npx_bin),
        }
