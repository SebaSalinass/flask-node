import json
import shutil

import pytest
from flask import Flask

from flask_node import ConfigurationError, DependencyConflictError, Node


def setup(tmp_path, runner, content):
    project = tmp_path / "pyproject.toml"
    project.write_text(content)
    app = Flask(__name__, root_path=str(tmp_path))
    node = Node(app, runner=runner)
    return app, node.get_manager(app), project


def test_reconstruct_and_prune(tmp_path, runner):
    content = """[tool.flask-node]
version = 1
[tool.flask-node.packages]
leaflet = "^1.9"
"chart.js" = "^4.5"
[tool.flask-node.dev-packages]
tailwindcss = "^4.1"
"""
    app, manager, project = setup(tmp_path, runner, content)
    manager.require("@tailwindcss/cli", "^4.1", dev=True)
    manager.require("leaflet", "^1.9")
    assert not manager.directory.exists()
    runner.run.assert_not_called()
    snapshot = manager.requirements
    snapshot.clear()
    assert "leaflet" in manager.requirements
    assert app.test_cli_runner().invoke(args=["node", "sync"]).exit_code == 0
    first = manager.manifest_path.read_bytes()
    data = json.loads(first)
    assert list(data["dependencies"]) == ["chart.js", "leaflet"]
    assert data["devDependencies"] == {
        "@tailwindcss/cli": "^4.1",
        "tailwindcss": "^4.1",
    }
    assert runner.run.call_args.kwargs["capture_output"] is False
    shutil.rmtree(manager.directory)
    _, recreated, _ = setup(tmp_path, runner, content)
    recreated.require("@tailwindcss/cli", "^4.1", dev=True)
    recreated.sync()
    assert recreated.manifest_path.read_bytes() == first
    recreated.manifest_path.write_text('{"dependencies": {"stale": "1"}}')
    recreated.sync()
    assert recreated.manifest_path.read_bytes() == first
    assert project.read_text() == content


@pytest.mark.parametrize(
    "declaration",
    [
        "version = 2",
        "version = true",
        "packages = []",
        "unknown = 1",
        "[packages]\nx = 2",
        '[packages]\nx = ""',
        '[packages]\n"../bad" = "1"',
        '[packages]\nx = "1"\n[dev-packages]\nx = "1"',
    ],
)
def test_invalid_configuration(tmp_path, runner, declaration):
    with pytest.raises((ConfigurationError, DependencyConflictError)):
        setup(
            tmp_path,
            runner,
            "[tool.flask-node]\n"
            + declaration.replace("[packages]", "[tool.flask-node.packages]").replace(
                "[dev-packages]", "[tool.flask-node.dev-packages]"
            ),
        )
    assert not (tmp_path / ".node").exists()
    runner.run.assert_not_called()


def test_conflicts_have_no_side_effects(tmp_path, runner):
    _, manager, _ = setup(tmp_path, runner, '[tool.flask-node.packages]\nx = "^1"')
    with pytest.raises(DependencyConflictError, match="x"):
        manager.require("x", "^2")
    with pytest.raises(DependencyConflictError):
        manager.require("x", "^1", dev=True)
    assert manager.requirements["x"].version == "^1"
    runner.run.assert_not_called()


def test_explicit_project_path_and_app_isolation(tmp_path, runner):
    project = tmp_path / "pyproject.toml"
    project.write_text('[tool.flask-node.packages]\nx = "1"')
    app = Flask("nested", root_path=str(tmp_path / "app"))
    app.config["NODE_PYPROJECT"] = "../pyproject.toml"
    node = Node(app, runner=runner)
    assert node.get_manager(app).requirements["x"].version == "1"
    other = Flask("other", root_path=str(tmp_path / "other"))
    node.init_app(other)
    assert node.get_manager(other).requirements == {}


def test_malformed_toml(tmp_path, runner):
    with pytest.raises(ConfigurationError, match="pyproject.toml"):
        setup(tmp_path, runner, "[broken")
