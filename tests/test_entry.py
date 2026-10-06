import json
import shutil
from pathlib import Path

import pytest
from flask import Flask

from flask_node import (
    AssetResolutionError,
    CommandExecutionError,
    CommandResult,
    CommandRunner,
    ConfigurationError,
    EntryResolutionError,
    ExecutableNotFoundError,
    Node,
    NodeManager,
    PackageNotFoundError,
)


def installed(manager, name="example", **manifest):
    root = manager.directory / "node_modules" / name
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"version": "1", **manifest}))
    for filename in ("index.js", "plugin.js", "require.cjs", "import.mjs", "main.js"):
        # Loading this code would fail, proving resolution does not evaluate it.
        (root / filename).write_text("throw new Error('PACKAGE EXECUTED');")
    return root


def response(runner, path):
    runner.run.return_value = CommandResult(
        ("node",), 0, json.dumps({"path": str(path)})
    )


@pytest.mark.parametrize(
    "name,subpath", [("example", None), ("@scope/example", None), ("example", "plugin")]
)
def test_boundary(manager, runner, name, subpath):
    root = installed(manager, name)
    target = root / ("plugin.js" if subpath else "index.js")
    response(runner, target)
    assert manager.resolve_entry(name, subpath) == target
    executable, args = runner.run.call_args.args
    assert executable == manager.node_bin
    assert args[-2:] == (
        str(manager.directory / ".flask-node-resolver.cjs"),
        name + (f"/{subpath}" if subpath else ""),
    )
    assert runner.run.call_args.kwargs == {
        "cwd": manager.directory,
        "capture_output": True,
    }
    assert not manager.manifest_path.exists()
    assert not (manager.directory / ".flask-node-resolver.cjs").exists()
    runner.locate.assert_not_called()


@pytest.mark.parametrize(
    "name", [None, "", "../x", "/x", "x/plugin", "node:fs", "@scope/../x", "C:\\x"]
)
def test_invalid_name(manager, runner, name):
    with pytest.raises(ConfigurationError):
        manager.resolve_entry(name)
    runner.run.assert_not_called()
    assert not manager.directory.exists()


@pytest.mark.parametrize(
    "subpath",
    [
        "",
        ".",
        "..",
        "../x",
        "x/../y",
        "/x",
        "C:/x",
        "x\\y",
        "x//y",
        "./x",
        "x/",
        "\x00",
        "%2e%2e/x",
        "x%2fy",
        1,
        Path("plugin"),
    ],
)
def test_invalid_subpath(manager, runner, subpath):
    with pytest.raises(EntryResolutionError):
        manager.resolve_entry("example", subpath)
    runner.run.assert_not_called()
    assert not manager.directory.exists()


def test_missing_package(manager, runner):
    with pytest.raises(PackageNotFoundError):
        manager.resolve_entry("example")
    runner.run.assert_not_called()
    assert not manager.directory.exists()


@pytest.mark.parametrize("value", ["fs", "node:fs", "relative.js", None])
def test_unsupported_results(manager, runner, value):
    installed(manager)
    runner.run.return_value = CommandResult(("node",), 0, json.dumps({"path": value}))
    with pytest.raises(EntryResolutionError):
        manager.resolve_entry("example")


@pytest.mark.parametrize("output", ["", "garbage", "[]", '{"error": null}'])
def test_malformed_response(manager, runner, output):
    installed(manager)
    runner.run.return_value = CommandResult(("node",), 0, output, "diagnostic")
    with pytest.raises(EntryResolutionError, match="diagnostic"):
        manager.resolve_entry("example")


@pytest.mark.parametrize("code", ["MODULE_NOT_FOUND", "ERR_PACKAGE_PATH_NOT_EXPORTED"])
def test_node_error(manager, runner, code):
    installed(manager)
    runner.run.return_value = CommandResult(
        ("node",), 0, json.dumps({"error": {"code": code, "message": "blocked entry"}})
    )
    with pytest.raises(EntryResolutionError, match=f"{code}: blocked entry"):
        manager.resolve_entry("example", "plugin")


@pytest.mark.parametrize(
    "error",
    [
        ExecutableNotFoundError("missing node"),
        CommandExecutionError(
            "failed",
            args=("node",),
            cwd="managed",
            returncode=7,
            stdout="out",
            stderr="err",
        ),
    ],
)
def test_runner_errors_preserved(manager, runner, error):
    installed(manager)
    runner.run.side_effect = error
    with pytest.raises(type(error)) as caught:
        manager.resolve_entry("example")
    assert caught.value is error


def test_missing_executable(manager, monkeypatch):
    installed(manager)
    manager.runner = CommandRunner()
    monkeypatch.setattr("flask_node.runner.shutil.which", lambda executable: None)
    with pytest.raises(ExecutableNotFoundError):
        manager.resolve_entry("example")


@pytest.mark.parametrize(
    "kind", ["outside", "sibling", "directory", "missing", "symlink"]
)
def test_containment_and_files(manager, runner, tmp_path, kind):
    root = installed(manager)
    outside = tmp_path / "outside.js"
    outside.write_text("outside")
    if kind == "sibling":
        target = installed(manager, "other") / "index.js"
    elif kind == "directory":
        target = root
    elif kind == "missing":
        target = root / "missing.js"
    elif kind == "symlink":
        target = root / "link.js"
        target.symlink_to(outside)
    else:
        target = outside
    response(runner, target)
    with pytest.raises(EntryResolutionError):
        manager.resolve_entry("example")


@pytest.mark.parametrize("kind", ["modules", "package", "manifest"])
def test_preflight_symlink_escape(manager, runner, tmp_path, kind):
    root = installed(manager)
    if kind == "modules":
        shutil.rmtree(manager.directory / "node_modules")
        (manager.directory / "node_modules").symlink_to(
            tmp_path, target_is_directory=True
        )
    elif kind == "package":
        shutil.rmtree(root)
        root.symlink_to(tmp_path, target_is_directory=True)
    else:
        (root / "package.json").unlink()
        (root / "package.json").symlink_to(tmp_path / "outside.json")
    with pytest.raises(AssetResolutionError):
        manager.resolve_entry("example")
    runner.run.assert_not_called()


def test_facade_isolation(tmp_path, runner):
    node = Node(runner=runner)
    for name in ("one", "two"):
        app = Flask(name, root_path=str(tmp_path / name))
        app.config["NODE_DIR"] = "custom"
        node.init_app(app)
        runner.run.assert_not_called()
        manager = node.get_manager(app)
        assert not manager.directory.exists()
        root = installed(manager)
        response(runner, root / "plugin.js")
        with app.app_context():
            assert node.resolve_entry("example", "plugin") == root / "plugin.js"
        assert runner.run.call_args.kwargs["cwd"] == tmp_path / name / "custom"
        runner.reset_mock()


@pytest.fixture
def real_manager(tmp_path):
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node executable unavailable: offline entry integration skipped")
    return NodeManager(tmp_path / "custom-managed", node_bin=executable)


@pytest.mark.parametrize(
    "name,subpath,manifest,expected",
    [
        ("example", None, {}, "index.js"),
        ("@scope/example", None, {"main": "main"}, "main.js"),
        ("example", "plugin", {}, "plugin.js"),
        (
            "example",
            None,
            {"main": "main.js", "exports": "./require.cjs"},
            "require.cjs",
        ),
        (
            "example",
            None,
            {
                "exports": {
                    "import": "./import.mjs",
                    "require": "./require.cjs",
                    "default": "./main.js",
                }
            },
            "require.cjs",
        ),
        (
            "example",
            None,
            {"exports": {"node": "./main.js", "default": "./index.js"}},
            "main.js",
        ),
        ("example", None, {"exports": {"default": "./main.js"}}, "main.js"),
        (
            "@scope/example",
            "plugin",
            {"exports": {"./plugin": "./require.cjs"}},
            "require.cjs",
        ),
    ],
)
def test_offline_real_resolution(
    real_manager, tmp_path, monkeypatch, name, subpath, manifest, expected
):
    root = installed(real_manager, name, **manifest)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    before = {
        p: p.read_bytes() for p in real_manager.directory.rglob("*") if p.is_file()
    }
    assert real_manager.resolve_entry(name, subpath) == root / expected
    after = {
        p: p.read_bytes() for p in real_manager.directory.rglob("*") if p.is_file()
    }
    assert before == after


@pytest.mark.parametrize(
    "manifest,subpath",
    [
        ({}, "missing"),
        ({"exports": {".": "./index.js"}}, "plugin"),
        ({"exports": {"import": "./import.mjs"}}, None),
        ({"exports": "./missing.js"}, None),
        ({"exports": "./main"}, None),
        ({"exports": {"./plugin": None}}, "plugin"),
    ],
)
def test_offline_missing_or_blocked(real_manager, manifest, subpath):
    installed(real_manager, **manifest)
    with pytest.raises(EntryResolutionError, match="example"):
        real_manager.resolve_entry("example", subpath)


def test_offline_builtin(real_manager):
    installed(real_manager, "fs")
    with pytest.raises(EntryResolutionError, match="ERR_UNSUPPORTED_BUILTIN"):
        real_manager.resolve_entry("fs")


def test_offline_internal_symlink(real_manager):
    root = installed(real_manager)
    (root / "plugin.js").unlink()
    (root / "plugin.js").symlink_to(root / "index.js")
    assert real_manager.resolve_entry("example", "plugin") == root / "index.js"


def test_offline_directory_index(real_manager):
    root = installed(real_manager)
    (root / "plugin.js").unlink()
    (root / "plugin").mkdir()
    target = root / "plugin/index.js"
    target.write_text("throw new Error('PACKAGE EXECUTED');")
    assert real_manager.resolve_entry("example", "plugin") == target


def test_offline_entry_symlink_escape(real_manager, tmp_path):
    root = installed(real_manager)
    outside = tmp_path / "outside.js"
    outside.write_text("throw new Error('PACKAGE EXECUTED');")
    (root / "index.js").unlink()
    (root / "index.js").symlink_to(outside)
    with pytest.raises(EntryResolutionError, match="escapes"):
        real_manager.resolve_entry("example")


def test_no_ancestor_fallback(real_manager, tmp_path):
    ancestor = NodeManager(tmp_path)
    installed(ancestor)
    with pytest.raises(PackageNotFoundError):
        real_manager.resolve_entry("example")
    assert not real_manager.directory.exists()


def test_offline_exports_directory_rejected(real_manager):
    installed(real_manager, exports="./")
    with pytest.raises(EntryResolutionError):
        real_manager.resolve_entry("example")


def test_resolution_error_retains_stderr(manager, runner):
    installed(manager)
    runner.run.return_value = CommandResult(
        ("node",),
        0,
        json.dumps({"error": {"code": "MODULE_NOT_FOUND", "message": "missing"}}),
        "runtime diagnostic",
    )
    with pytest.raises(EntryResolutionError, match="runtime diagnostic"):
        manager.resolve_entry("example")


def test_explicit_asset_ignores_exports(real_manager):
    root = installed(real_manager, exports={".": "./index.js"})
    assert real_manager.resolve("example", "plugin.js") == root / "plugin.js"
    with pytest.raises(EntryResolutionError, match="ERR_PACKAGE_PATH_NOT_EXPORTED"):
        real_manager.resolve_entry("example", "plugin")
