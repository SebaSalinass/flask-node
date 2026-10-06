import json

import pytest

from flask_node import AssetResolutionError, PackageNotFoundError


def installed(manager, name):
    root = manager.directory / "node_modules" / name
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": name, "version": "1.0.0"}))
    (root / "dist").mkdir()
    (root / "dist" / "file.js").write_text("content")
    return root


@pytest.mark.parametrize("name", ["example", "@scope/example"])
def test_package_and_asset(manager, name):
    root = installed(manager, name)
    package = manager.package(name)
    assert package.version == "1.0.0"
    assert package.root == root
    assert manager.resolve(name, "dist/file.js") == root / "dist/file.js"


@pytest.mark.parametrize(
    "path",
    [
        "../package.json",
        "/etc/passwd",
        "dist/../../outside",
        "C:\\temp\\file",
        "..\\file",
    ],
)
def test_traversal(manager, path):
    installed(manager, "example")
    with pytest.raises(AssetResolutionError):
        manager.resolve("example", path)


def test_missing(manager):
    with pytest.raises(PackageNotFoundError):
        manager.package("example")
    installed(manager, "example")
    with pytest.raises(AssetResolutionError):
        manager.resolve("example", "missing")


def test_asset_symlink(manager, tmp_path):
    root = installed(manager, "example")
    outside = tmp_path / "secret"
    outside.write_text("secret")
    (root / "link").symlink_to(outside)
    with pytest.raises(AssetResolutionError):
        manager.resolve("example", "link")


def test_package_symlink(manager, tmp_path):
    modules = manager.directory / "node_modules"
    modules.mkdir(parents=True)
    (modules / "example").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(AssetResolutionError):
        manager.package("example")


def test_modules_symlink(manager, tmp_path):
    manager.directory.mkdir()
    (manager.directory / "node_modules").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(AssetResolutionError):
        manager.package("example")


def test_manifest_symlink(manager, tmp_path):
    root = installed(manager, "example")
    (root / "package.json").unlink()
    outside = tmp_path / "outside.json"
    outside.write_text('{"version": "1"}')
    (root / "package.json").symlink_to(outside)
    with pytest.raises(AssetResolutionError):
        manager.package("example")
