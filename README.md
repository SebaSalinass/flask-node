# Flask-Node

Flask-Node manages an isolated Node/npm project for Flask applications and
extensions. It contains no JavaScript library integrations, bundler, asset
server, or frontend framework.

Requires Python 3.10+ and Flask 2.2–3.x. Install Node.js (including npm/npx)
separately when executing commands; importing and initializing the Flask
extension does not require it.

```bash
pip install Flask-Node
```

## Application setup

```python
from flask import Flask
from flask_node import Node

node = Node()


def create_app():
    app = Flask(__name__)
    node.init_app(app)
    return app
```

`Node(app)` is also supported. `init_app()` registers defaults and the CLI,
without creating directories or launching commands. Each application owns a
separate `NodeManager` in `app.extensions["node"]`; a shared `Node` facade uses
the current application context. `node.get_manager(app)` gives explicit access
outside a context. Duplicate registration raises `ConfigurationError`.

## Configuration

| Setting | Default | Meaning |
| --- | --- | --- |
| `NODE_DIR` | `.node` | Relative to `app.root_path`, or an absolute path |
| `NODE_BIN` | `node` | Node executable name or path |
| `NODE_NPM_BIN` | `npm` | npm executable name or path |
| `NODE_NPX_BIN` | `npx` | npx executable name or path |

Configure before calling `init_app()`. Configuration is captured per app.
For a directory beside an application package, configure an absolute project
path. No behavior depends on the shell's current directory.

## Lifecycle and dependencies

```python
with app.app_context():
    node.require("example", version="^1")
    node.require("@scope/build-tool", version="^2", dev=True)
    node.initialize()
    node.install()
    node.install("another-package", version="^3")
    node.uninstall("another-package")
```

`require()` only records an in-memory declaration. Consumer extensions may call
it during application setup. It creates no files and does not check or install
packages. Identical declarations are idempotent; differing versions or dependency
sections raise `DependencyConflictError`. Version declarations are compared as
strings; Flask-Node does not solve semver ranges.

`initialize()` creates `.node/package.json` with `private: true` and empty
`dependencies` / `devDependencies`. It preserves an existing valid manifest
without rewriting it. Invalid manifests fail clearly. npm creates the lockfile
and installed modules later:

```text
.node/
    package.json
    package-lock.json
    node_modules/
```

`install()` initializes if necessary, merges active declarations into the
manifest, preserves unrelated fields and dependencies, and runs `npm install`.
Declarations take precedence over persisted entries for the same package.
`install(name, version=None, dev=False)` additionally installs a registry package;
without a version, npm chooses it unless an active declaration supplies one.
Conflicting explicit options fail before installation. Uninstalling an actively
required package is rejected. npm failures may leave manifest changes or partial
installation artifacts; operations are not transactional.

`ci()` requires `package-lock.json` and declarations matching the manifest, then
runs `npm ci` without rewriting the manifest. npm validates lockfile consistency.
Commit `.node/package.json` and `.node/package-lock.json` for reproducible builds;
ignore `.node/node_modules/`.

## Commands and diagnostics

```python
with app.app_context():
    result = node.npm("run", "custom-script")
    result = node.npx("some-tool", "--help", capture_output=False)
    print(node.status())
```

Raw commands require an initialized environment and run with its directory as
`cwd`. Arguments are passed individually with `shell=False`. Python calls capture
output by default; use `capture_output=False` to inherit terminal streams.
`CommandResult` exposes `args`, `returncode`, `stdout`, and `stderr`.

`status()` reports the directory, manifest presence, and executable locations
(or `None`). It launches no processes and does not validate executable versions.
Missing executables raise `ExecutableNotFoundError`; nonzero exits and other
launch failures raise `CommandExecutionError`, which retains `command`, `cwd`,
`returncode`, `stdout`, and `stderr`. All public errors derive from `NodeError`.

npm/npx may access the network and run package scripts. The managed working
directory is not a process sandbox; invoked tools can write elsewhere.

## Flask CLI

```bash
flask --app your_app node init
flask --app your_app node install
flask --app your_app node install example --version '^1' --dev
flask --app your_app node uninstall example
flask --app your_app node npm -- run custom-script --flag
flask --app your_app node npx -- some-tool --help
flask --app your_app node ci
flask --app your_app node status
```

CLI commands use the same Python operations, stream subprocess output, and
report extension errors with a nonzero exit status. `--` separates forwarding
arguments from Click's own options.

## Installed assets and extension consumers

```python
manager = app.extensions["node"]
manager.require("example", "^1")  # Safe during consumer init_app().

# After an explicit installation step:
asset = manager.resolve("example", "dist/example.js")
package = manager.package("example")
assert package.resolve("dist/example.js") == asset
print(package.name, package.version, package.root)
```

The consumer must initialize Flask-Node first. It owns its library-specific
configuration, rendering, asset copying/serving, and build/watch commands.
Flask-Node only declares/installs dependencies, executes commands, and locates
files. No registration protocol is needed.

Package lookup supports ordinary and scoped registry names. Asset lookup returns
an existing `Path`; absolute paths, parent traversal, Windows-style paths, and
symlinks escaping the package or managed environment are rejected. Externally
linked packages are intentionally unsupported. Missing or malformed installed
packages raise `PackageNotFoundError`; unsafe or missing assets raise
`AssetResolutionError`. This is filesystem path validation, not protection
against concurrent malicious filesystem changes.

## Development

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]' build
.venv/bin/python -m pytest
.venv/bin/python -m build
```

Tests inject/mock the runner and subprocess boundary. They never download npm
packages or require Node. A custom runner can be supplied to `Node(runner=...)`
or `NodeManager(..., runner=...)` for testing. This dependency injection is not a
consumer plugin protocol.

Inspired by [Flask-Tailwind-Manager](https://github.com/SebaSalinass/flask-tailwind-manager).
