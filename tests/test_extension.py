from pathlib import Path

import pytest
from flask import Flask

from flask_node import ConfigurationError, Node, NodeManager


def test_registration_has_no_side_effects(app, runner, tmp_path):
    assert isinstance(app.extensions["node"], NodeManager)
    assert app.config["NODE_DIR"] == ".node"
    assert app.config["NODE_BIN"] == "node"
    assert app.extensions["node"].directory == tmp_path / ".node"
    assert not (tmp_path / ".node").exists()
    runner.run.assert_not_called()
    runner.locate.assert_not_called()


def test_factory_multi_app(tmp_path):
    node = Node()

    def create(name):
        app = Flask(name, root_path=str(tmp_path / name), static_folder=None)
        node.init_app(app)
        return app

    one, two = create("one"), create("two")
    with one.app_context():
        node.require("example", "^1")
        node.initialize()
        assert node.get_manager() is one.extensions["node"]
    with two.app_context():
        node.require("example", "^2")
        assert node.get_manager() is two.extensions["node"]
        assert not node.get_manager().directory.exists()
    assert node.get_manager(one) is one.extensions["node"]


@pytest.mark.parametrize(
    "directory", ["custom", Path("custom"), "/tmp/flask-node-explicit"]
)
def test_custom_directory(tmp_path, directory):
    app = Flask(__name__, root_path=str(tmp_path))
    app.config["NODE_DIR"] = directory
    Node(app)
    expected = (
        Path(directory) if Path(directory).is_absolute() else tmp_path / directory
    )
    assert app.extensions["node"].directory == expected


def test_duplicate_and_unregistered(app):
    with pytest.raises(ConfigurationError):
        Node(app)
    with pytest.raises(ConfigurationError):
        Node().get_manager(Flask("other"))
    with pytest.raises(RuntimeError):
        Node().status()


@pytest.mark.parametrize(
    "key,value", [("NODE_DIR", ""), ("NODE_DIR", None), ("NODE_NPM_BIN", "")]
)
def test_invalid_config(key, value):
    app = Flask(__name__)
    app.config[key] = value
    with pytest.raises(ConfigurationError):
        Node(app)
    assert "node" not in app.extensions
