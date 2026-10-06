"""Flask integration with no initialization side effects."""

from pathlib import Path
from typing import Any

from flask import Flask, current_app

from .exceptions import ConfigurationError
from .manager import NodeManager
from .package import Package
from .runner import CommandResult, CommandRunner


class Node:
    def __init__(
        self, app: Flask | None = None, *, runner: CommandRunner | None = None
    ):
        self._runner = runner
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        if "node" in app.extensions:
            raise ConfigurationError(
                "Flask-Node is already initialized on this application."
            )
        defaults = {
            "NODE_DIR": ".node",
            "NODE_PYPROJECT": "pyproject.toml",
            "NODE_BIN": "node",
            "NODE_NPM_BIN": "npm",
            "NODE_NPX_BIN": "npx",
        }
        for key, default in defaults.items():
            app.config.setdefault(key, default)
        value = app.config["NODE_DIR"]
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ConfigurationError("NODE_DIR must be a nonempty path.")
        directory = Path(value)
        if not directory.is_absolute():
            directory = Path(app.root_path) / directory
        for key in ("NODE_BIN", "NODE_NPM_BIN", "NODE_NPX_BIN"):
            if not isinstance(app.config[key], str) or not app.config[key].strip():
                raise ConfigurationError(f"{key} must be a nonempty executable path.")
        project_value = app.config["NODE_PYPROJECT"]
        if not isinstance(project_value, (str, Path)) or not str(project_value).strip():
            raise ConfigurationError("NODE_PYPROJECT must be a nonempty path.")
        pyproject = Path(project_value)
        if not pyproject.is_absolute():
            pyproject = Path(app.root_path) / pyproject
        app.extensions["node"] = NodeManager(
            directory,
            node_bin=app.config["NODE_BIN"],
            npm_bin=app.config["NODE_NPM_BIN"],
            npx_bin=app.config["NODE_NPX_BIN"],
            runner=self._runner,
            pyproject=pyproject.resolve(),
        )
        from .cli import node_cli

        app.cli.add_command(node_cli)

    def get_manager(self, app: Flask | None = None) -> NodeManager:
        application = app if app is not None else current_app
        manager = application.extensions.get("node")
        if not isinstance(manager, NodeManager):
            raise ConfigurationError("Initialize Flask-Node before using its API.")
        return manager

    # Delegate the documented manager API while keeping application state local.
    def initialize(self) -> Path:
        return self.get_manager().initialize()

    def require(self, name: str, version: str = "*", *, dev: bool = False) -> None:
        return self.get_manager().require(name, version, dev=dev)

    @property
    def requirements(self):
        return self.get_manager().requirements

    def sync(self, *, capture_output: bool = True) -> CommandResult:
        return self.get_manager().sync(capture_output=capture_output)

    def install(
        self,
        name: str | None = None,
        version: str | None = None,
        *,
        dev: bool = False,
        capture_output: bool = True,
    ) -> CommandResult:
        return self.get_manager().install(
            name, version, dev=dev, capture_output=capture_output
        )

    def uninstall(self, name: str, *, capture_output: bool = True) -> CommandResult:
        return self.get_manager().uninstall(name, capture_output=capture_output)

    def npm(self, *args: str, capture_output: bool = True) -> CommandResult:
        return self.get_manager().npm(*args, capture_output=capture_output)

    def npx(self, *args: str, capture_output: bool = True) -> CommandResult:
        return self.get_manager().npx(*args, capture_output=capture_output)

    def ci(self, *, capture_output: bool = True) -> CommandResult:
        return self.get_manager().ci(capture_output=capture_output)

    def package(self, name: str) -> Package:
        return self.get_manager().package(name)

    def resolve(self, name: str, asset: str | Path) -> Path:
        return self.get_manager().resolve(name, asset)

    def status(self) -> dict[str, Any]:
        return self.get_manager().status()
