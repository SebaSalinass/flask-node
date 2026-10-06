from unittest.mock import Mock

import pytest
from flask import Flask

from flask_node import CommandResult, CommandRunner, Node


@pytest.fixture
def runner():
    fake = Mock(spec=CommandRunner)
    fake.run.return_value = CommandResult(("npm",), 0)
    fake.locate.side_effect = lambda executable: f"/bin/{executable}"
    return fake


@pytest.fixture
def app(tmp_path, runner):
    app = Flask(__name__, root_path=str(tmp_path))
    Node(app, runner=runner)
    return app


@pytest.fixture
def manager(app):
    return app.extensions["node"]
