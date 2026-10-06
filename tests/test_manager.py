import json

import pytest

from flask_node import ConfigurationError, DependencyConflictError, EnvironmentError


def test_initialize_idempotent(manager, runner):
    directory = manager.initialize()
    assert json.loads(manager.manifest_path.read_text())["private"] is True
    original = '{"scripts": {"x": "echo x"}, "dependencies": {"existing": "^2"}}'
    manager.manifest_path.write_text(original)
    manager.initialize()
    assert manager.manifest_path.read_text() == original
    assert not (directory / "package-lock.json").exists()
    runner.run.assert_not_called()


@pytest.mark.parametrize(
    "manifest",
    ["broken", "[]", '{"dependencies": []}', '{"devDependencies": {"x": 2}}'],
)
def test_invalid_manifest(manager, manifest):
    manager.directory.mkdir()
    manager.manifest_path.write_text(manifest)
    with pytest.raises(EnvironmentError):
        manager.initialize()
    assert manager.manifest_path.read_text() == manifest


def test_declarations_and_install(manager, runner):
    manager.require("example", "^1")
    manager.require("example", "^1")
    manager.require("@scope/tool", "^2", dev=True)
    assert not manager.directory.exists()
    manager.install()
    data = json.loads(manager.manifest_path.read_text())
    assert data["dependencies"] == {"example": "^1"}
    assert data["devDependencies"] == {"@scope/tool": "^2"}
    runner.run.assert_called_once_with(
        "npm", ("install",), cwd=manager.directory, capture_output=True
    )


def test_install_preserves_fields_and_moves_section(manager):
    manager.initialize()
    manager.manifest_path.write_text(
        json.dumps(
            {
                "scripts": {"a": "b"},
                "dependencies": {"other": "1"},
                "devDependencies": {"example": "^0"},
            }
        )
    )
    manager.require("example", "^1")
    manager.install()
    data = json.loads(manager.manifest_path.read_text())
    assert data["scripts"] == {"a": "b"}
    assert data["dependencies"] == {"other": "1", "example": "^1"}
    assert "example" not in data["devDependencies"]


@pytest.mark.parametrize(
    "name,version,dev,spec",
    [
        ("example", "^4", False, "example@^4"),
        ("@scope/tool", None, True, "@scope/tool"),
    ],
)
def test_explicit_install(manager, runner, name, version, dev, spec):
    manager.install(name, version, dev=dev)
    args = ("install", "--save-dev" if dev else "--save-prod", "--", spec)
    runner.run.assert_called_once_with(
        "npm", args, cwd=manager.directory, capture_output=True
    )


def test_conflicts(manager, runner):
    manager.require("example", "^1")
    with pytest.raises(DependencyConflictError):
        manager.require("example", "^2")
    with pytest.raises(DependencyConflictError):
        manager.install("example", "^2")
    with pytest.raises(DependencyConflictError):
        manager.uninstall("example")
    runner.run.assert_not_called()


def test_remove_and_command_passthrough(manager, runner):
    with pytest.raises(EnvironmentError):
        manager.npm("install")
    manager.initialize()
    manager.uninstall("example")
    assert runner.run.call_args.args == ("npm", ("uninstall", "--", "example"))
    manager.npx("tool", "--flag", "argument with spaces", capture_output=False)
    assert runner.run.call_args.args == (
        "npx",
        ("tool", "--flag", "argument with spaces"),
    )
    assert runner.run.call_args.kwargs["capture_output"] is False


def test_ci(manager, runner):
    manager.initialize()
    manager.require("example", "^1")
    with pytest.raises(EnvironmentError):
        manager.ci()
    (manager.directory / "package-lock.json").write_text("{}")
    with pytest.raises(DependencyConflictError):
        manager.ci()
    manager.install()
    manager.ci()
    assert runner.run.call_args.args == ("npm", ("ci",))


def test_status(manager, runner):
    result = manager.status()
    assert result["npm"] == "/bin/npm"
    assert result["initialized"] is False
    runner.run.assert_not_called()
    runner.locate.return_value = None
    runner.locate.side_effect = None
    assert manager.status()["node"] is None


@pytest.mark.parametrize(
    "name", ["../evil", "-x", "foo/bar", "@scope/../x", "/absolute"]
)
def test_bad_package_names(manager, name):
    with pytest.raises(ConfigurationError):
        manager.install(name)
    assert not manager.directory.exists()


@pytest.mark.parametrize("version", ["", None, 2])
def test_bad_versions(manager, version):
    with pytest.raises(ConfigurationError):
        manager.require("example", version)


def test_bad_install_options(manager):
    with pytest.raises(ConfigurationError):
        manager.install(version="1")
