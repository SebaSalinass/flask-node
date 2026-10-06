"""Thin Flask CLI adapters."""

import json
from functools import wraps

import click
from flask import current_app
from flask.cli import with_appcontext

from .exceptions import NodeError


def operation(function):
    @wraps(function)
    @with_appcontext
    def wrapped(*args, **kwargs):
        try:
            return function(current_app.extensions["node"], *args, **kwargs)
        except NodeError as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapped


@click.group("node")
def node_cli():
    """Manage the application's isolated Node environment."""


@node_cli.command("init")
@operation
def initialize(manager):
    """Create or validate the managed package manifest."""
    click.echo(f"Initialized {manager.initialize()}")


@node_cli.command()
@operation
def sync(manager):
    """Rebuild the managed manifest from application and extension declarations."""
    manager.sync(capture_output=False)


@node_cli.command()
@click.argument("package", required=False)
@click.option("--version")
@click.option("--dev", is_flag=True)
@operation
def install(manager, package, version, dev):
    """Install declarations or a registry package."""
    manager.install(package, version, dev=dev, capture_output=False)


@node_cli.command()
@click.argument("package")
@operation
def uninstall(manager, package):
    """Remove an npm dependency."""
    manager.uninstall(package, capture_output=False)


@node_cli.command()
@operation
def ci(manager):
    """Install reproducibly from the existing lockfile."""
    manager.ci(capture_output=False)


@node_cli.command()
@operation
def status(manager):
    """Show environment and executable locations without launching commands."""
    click.echo(json.dumps(manager.status(), indent=2))


@node_cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@operation
def npm(manager, args):
    """Forward arguments to npm in the managed directory."""
    manager.npm(*args, capture_output=False)


@node_cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@operation
def npx(manager, args):
    """Forward arguments to npx in the managed directory."""
    manager.npx(*args, capture_output=False)
