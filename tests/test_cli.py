import pytest

from flask_node import ExecutableNotFoundError


def test_init_and_status(app, runner):
    cli = app.test_cli_runner()
    assert cli.invoke(args=["node", "init"]).exit_code == 0
    assert cli.invoke(args=["node", "init"]).exit_code == 0
    result = cli.invoke(args=["node", "status"])
    assert result.exit_code == 0
    assert '"initialized": true' in result.output
    runner.run.assert_not_called()


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["install"], ("install",)),
        (
            ["install", "example", "--version", "^1", "--dev"],
            ("install", "--save-dev", "--", "example@^1"),
        ),
        (["uninstall", "example"], ("uninstall", "--", "example")),
        (["npm", "--", "run", "x", "--flag"], ("run", "x", "--flag")),
        (["npx", "tool", "--flag", "with spaces"], ("tool", "--flag", "with spaces")),
    ],
)
def test_commands(app, manager, runner, arguments, expected):
    manager.initialize()
    result = app.test_cli_runner().invoke(args=["node", *arguments])
    assert result.exit_code == 0, result.output
    assert runner.run.call_args.args == (
        "npx" if arguments[0] == "npx" else "npm",
        expected,
    )
    assert runner.run.call_args.kwargs["capture_output"] is False


def test_errors(app, manager, runner):
    cli = app.test_cli_runner()
    result = cli.invoke(args=["node", "npm", "run", "x"])
    assert result.exit_code == 1
    assert "flask node init" in result.output
    manager.initialize()
    runner.run.side_effect = ExecutableNotFoundError("npm missing")
    result = cli.invoke(args=["node", "install"])
    assert result.exit_code == 1
    assert "npm missing" in result.output


def test_ci(app, manager, runner):
    manager.initialize()
    (manager.directory / "package-lock.json").write_text("{}")
    result = app.test_cli_runner().invoke(args=["node", "ci"])
    assert result.exit_code == 0
    assert runner.run.call_args.args == ("npm", ("ci",))
