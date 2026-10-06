import subprocess
from unittest.mock import Mock

import pytest

from flask_node import CommandExecutionError, CommandRunner, ExecutableNotFoundError


def test_execution(monkeypatch, tmp_path):
    monkeypatch.setattr("flask_node.runner.shutil.which", lambda name: "/bin/npm")
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "output", ""))
    monkeypatch.setattr("flask_node.runner.subprocess.run", run)
    result = CommandRunner().run("npm", ("run", "a; echo unsafe"), cwd=tmp_path)
    run.assert_called_once_with(
        ("/bin/npm", "run", "a; echo unsafe"),
        cwd=tmp_path,
        shell=False,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.stdout == "output"


def test_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("flask_node.runner.shutil.which", lambda name: None)
    with pytest.raises(ExecutableNotFoundError, match="Install Node"):
        CommandRunner().run("npm", (), cwd=tmp_path)


@pytest.mark.parametrize(
    "error", [FileNotFoundError("gone"), PermissionError("denied")]
)
def test_launch_errors(monkeypatch, tmp_path, error):
    monkeypatch.setattr("flask_node.runner.shutil.which", lambda name: "/bin/npm")
    monkeypatch.setattr("flask_node.runner.subprocess.run", Mock(side_effect=error))
    with pytest.raises(
        ExecutableNotFoundError
        if isinstance(error, FileNotFoundError)
        else CommandExecutionError
    ):
        CommandRunner().run("npm", (), cwd=tmp_path)


def test_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr("flask_node.runner.shutil.which", lambda name: "/bin/npm")
    monkeypatch.setattr(
        "flask_node.runner.subprocess.run",
        Mock(return_value=subprocess.CompletedProcess([], 7, "out", "failure")),
    )
    with pytest.raises(CommandExecutionError, match="failure") as caught:
        CommandRunner().run("npm", ("install",), cwd=tmp_path)
    assert caught.value.returncode == 7
    assert caught.value.stderr == "failure"
    assert caught.value.command == ("/bin/npm", "install")
