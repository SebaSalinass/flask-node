import json
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask, url_for

from flask_node import (
    AssetConflictError,
    AssetPublicationError,
    AssetResolutionError,
    Node,
    PackageNotFoundError,
)


def installed(manager, name="library"):
    root = manager.directory / "node_modules" / name
    root.mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"version": "1.0.0"}))
    (root / "dist" / "images" / "nested").mkdir(parents=True)
    (root / "dist" / "library.js").write_text("new js")
    (root / "dist" / "images" / "nested" / "icon.png").write_bytes(b"icon")
    return root


def test_registration_and_isolation(app, manager, runner, tmp_path):
    asset = manager.register_asset("library", "./dist/library.js", "vendor/library.js")
    assert (
        manager.register_asset("library", "dist/library.js", "./vendor/library.js")
        == asset
    )
    assert manager.assets == (asset,)
    assert manager.requirements == {}
    assert not manager.directory.exists()
    assert not Path(app.static_folder).exists()
    runner.run.assert_not_called()
    node = Node()
    other = Flask("other", root_path=str(tmp_path / "other"))
    node.init_app(other)
    assert node.get_manager(other).assets == ()
    with app.app_context():
        assert node.assets == (asset,)


@pytest.mark.parametrize(
    "destination", ["vendor/common.js", "vendor", "vendor/common.js/child"]
)
def test_conflicts(manager, destination):
    manager.register_asset("one", "x", "vendor/common.js")
    with pytest.raises(AssetConflictError):
        manager.register_asset("two", "y", destination)
    with pytest.raises(AssetConflictError):
        manager.publish_asset("two", "y", destination)


def test_file_directory_and_replacement(app, manager, runner):
    root = installed(manager, "@scope/library")
    manager.register_asset("@scope/library", "dist/images", "vendor/images")
    manager.register_asset("@scope/library", "dist/library.js", "vendor/library.js")
    targets = manager.publish_assets()
    assert [p.name for p in targets] == ["images", "library.js"]
    static = Path(app.static_folder)
    assert (static / "vendor/images/nested/icon.png").read_bytes() == b"icon"
    (static / "vendor/images/stale.png").write_text("stale")
    (static / "unrelated.txt").write_text("keep")
    (root / "dist/library.js").write_text("updated")
    manager.publish_assets()
    assert not (static / "vendor/images/stale.png").exists()
    assert (static / "vendor/library.js").read_text() == "updated"
    assert (static / "unrelated.txt").read_text() == "keep"
    runner.run.assert_not_called()


def test_custom_static_factory_and_low_level(tmp_path, runner):
    node = Node(runner=runner)

    def create():
        app = Flask("factory", root_path=str(tmp_path), static_folder="public")
        node.init_app(app)
        return app

    app = create()
    manager = node.get_manager(app)
    installed(manager)
    with app.app_context():
        asset = node.register_asset("library", "dist/library.js", "vendor/library.js")
        path = node.publish_asset(asset.package, asset.source, asset.destination)
        assert path == tmp_path / "public/vendor/library.js"
        assert node.publish_assets() == (path,)
    with app.test_request_context():
        assert (
            url_for("static", filename=asset.destination) == "/public/vendor/library.js"
        )


@pytest.mark.parametrize("field", ["source", "destination"])
@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "../secret",
        "/tmp/secret",
        "vendor/../../outside",
        "C:\\x",
        "..\\x",
        "\x00",
    ],
)
def test_path_rejection(manager, field, path):
    values = {
        "package": "library",
        "source": "dist/library.js",
        "destination": "vendor/library.js",
    }
    values[field] = path
    with pytest.raises(AssetResolutionError):
        manager.register_asset(**values)


def test_missing_sources_and_preflight(manager, app):
    with pytest.raises(PackageNotFoundError):
        manager.publish_asset("missing", "x", "vendor/x")
    installed(manager)
    manager.register_asset("library", "dist/library.js", "vendor/a.js")
    manager.register_asset("library", "missing", "vendor/z.js")
    with pytest.raises(AssetResolutionError):
        manager.publish_assets()
    assert not Path(app.static_folder).exists()


def test_no_static(tmp_path, runner):
    app = Flask("disabled", root_path=str(tmp_path), static_folder=None)
    node = Node(app, runner=runner)
    manager = node.get_manager(app)
    manager.register_asset("library", "x", "vendor/x")
    with pytest.raises(AssetPublicationError, match="static folder"):
        manager.publish_assets()


@pytest.mark.parametrize("nested", [False, True])
def test_source_symlinks(manager, tmp_path, nested):
    root = installed(manager)
    outside = tmp_path / "secret"
    outside.write_text("secret")
    location = root / ("dist/images/escape" if nested else "escape")
    location.symlink_to(outside)
    with pytest.raises(AssetResolutionError):
        manager.publish_asset(
            "library", "dist/images" if nested else "escape", "vendor/result"
        )


@pytest.mark.parametrize("nested", [False, True])
def test_destination_symlinks(manager, app, tmp_path, nested):
    installed(manager)
    static = Path(app.static_folder)
    (static / "vendor/images").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    if nested:
        (static / "vendor/images/link").symlink_to(outside, target_is_directory=True)
        source, destination = "dist/images", "vendor/images"
    else:
        (static / "vendor/link").symlink_to(outside, target_is_directory=True)
        source, destination = "dist/library.js", "vendor/link/file.js"
    with pytest.raises(AssetResolutionError):
        manager.publish_asset("library", source, destination)
    assert list(outside.iterdir()) == []


def test_copy_failure(manager):
    installed(manager)
    with (
        patch("flask_node.assets.shutil.copy2", side_effect=OSError("copy denied")),
        pytest.raises(AssetPublicationError, match="copy denied"),
    ):
        manager.publish_asset("library", "dist/library.js", "vendor/library.js")


def test_type_mismatch(manager, app):
    installed(manager)
    target = Path(app.static_folder) / "vendor/library.js"
    target.mkdir(parents=True)
    with pytest.raises(AssetPublicationError, match="types differ"):
        manager.publish_asset("library", "dist/library.js", "vendor/library.js")


def test_cli_integration(app, manager, runner):
    for name in ("preline", "leaflet"):
        root = installed(manager, name)
        if name == "preline":
            (root / "dist/preline.js").write_text("preline")
            manager.register_asset(name, "dist/preline.js", "vendor/preline/preline.js")
        else:
            for filename in ("leaflet.js", "leaflet.css"):
                (root / "dist" / filename).write_text(filename)
                manager.register_asset(
                    name, f"dist/{filename}", f"vendor/leaflet/{filename}"
                )
            manager.register_asset(name, "dist/images", "vendor/leaflet/images")
    result = app.test_cli_runner().invoke(args=["node", "publish"])
    assert result.exit_code == 0, result.output
    assert "4 assets published." in result.output
    assert "preline: dist/preline.js" in result.output
    static = Path(app.static_folder)
    assert sorted(
        p.relative_to(static).as_posix() for p in static.rglob("*") if p.is_file()
    ) == [
        "vendor/leaflet/images/nested/icon.png",
        "vendor/leaflet/leaflet.css",
        "vendor/leaflet/leaflet.js",
        "vendor/preline/preline.js",
    ]
    runner.run.assert_not_called()


def test_cli_empty_and_error(app, manager):
    cli = app.test_cli_runner()
    assert "0 assets published." in cli.invoke(args=["node", "publish"]).output
    manager.register_asset("missing", "x", "vendor/x")
    result = cli.invoke(args=["node", "publish"])
    assert result.exit_code == 1
    assert "missing" in result.output


def test_malformed_package_json(manager):
    root = installed(manager)
    (root / "package.json").write_text("broken")
    with pytest.raises(PackageNotFoundError):
        manager.publish_asset("library", "dist/library.js", "vendor/library.js")


def test_replacement_restores_previous_on_failure(manager, app):
    installed(manager)
    target = manager.publish_asset("library", "dist/library.js", "vendor/library.js")
    target.write_text("previous")
    original = Path.rename

    def fail_staged(path, destination):
        if path.name == "asset":
            raise OSError("rename denied")
        return original(path, destination)

    with (
        patch.object(Path, "rename", fail_staged),
        pytest.raises(AssetPublicationError, match="rename denied"),
    ):
        manager.publish_asset("library", "dist/library.js", "vendor/library.js")
    assert target.read_text() == "previous"
    assert list(target.parent.glob(".flask-node-*")) == []
