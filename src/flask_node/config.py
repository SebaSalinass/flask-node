"""Read application requirements without creating a Node environment."""

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from .exceptions import ConfigurationError


def read_configuration(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        config = data.get("tool", {}).get("flask-node", {})
        if not isinstance(config, dict):
            raise TypeError("tool.flask-node must be a table")
        unknown = config.keys() - {"version", "packages", "dev-packages"}
        if unknown:
            raise ValueError(
                f"Unknown Flask-Node settings: {', '.join(sorted(unknown))}"
            )
        version = config.get("version", 1)
        if type(version) is not int or version != 1:
            raise ValueError("tool.flask-node.version must be 1")
        for section in ("packages", "dev-packages"):
            packages = config.get(section, {})
            if not isinstance(packages, dict) or not all(
                isinstance(name, str) and isinstance(spec, str)
                for name, spec in packages.items()
            ):
                raise ValueError(f"{section} must map package names to version strings")
        return config
    except (OSError, ValueError, AttributeError) as exc:
        raise ConfigurationError(
            f"Cannot load Flask-Node configuration from {path}: {exc}"
        ) from exc
