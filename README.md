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
| `NODE_PYPROJECT` | `pyproject.toml` | Application configuration, relative to `app.root_path` or absolute |
| `NODE_BIN` | `node` | Node executable name or path |
| `NODE_NPM_BIN` | `npm` | npm executable name or path |
| `NODE_NPX_BIN` | `npx` | npx executable name or path |

Configure before calling `init_app()`. Configuration is captured per app.
For a directory beside an application package, configure an absolute project
path. No behavior depends on the shell's current directory.

## Declarative application requirements

Commit your application's `pyproject.toml` with:

```toml
[tool.flask-node]
version = 1

[tool.flask-node.packages]
leaflet = "^1.9"
"chart.js" = "^4.5"

[tool.flask-node.dev-packages]
tailwindcss = "^4.1"
"@tailwindcss/cli" = "^4.1"
```

Configuration is read and validated during `init_app()`, without creating files
or running npm. A missing file or table means no application declarations.
Unknown settings, unsupported schema versions, and invalid declarations fail
clearly. For a packaged Flask application, set `NODE_PYPROJECT` to the project
file (for example `../pyproject.toml`); paths never depend on the shell directory.
Restart the application after changing declarations.

Extensions continue to call `require()`. Their requirements remain in memory
and are never written to the application's TOML. `manager.requirements` (also
`node.requirements` in an app context) returns a sorted snapshot of the combined
requirements. Identical version strings and dependency sections merge; all other
duplicates raise `DependencyConflictError`, including potentially overlapping
semver ranges. Flask-Node does not attempt npm semver resolution.

```bash
flask --app your_app node sync
```

`sync()` generates a deterministic, private `.node/package.json` containing
exactly the effective declarations, then runs `npm install`. It removes stale
manifest dependencies and custom metadata/scripts. Declare every needed direct
package in TOML or in its owning extension before using sync. The `.node/`
directory is disposable: deleting it and running sync reconstructs the project.
Commit the TOML and Python dependencies; the generated manifest need not be
committed. The existing install/uninstall and raw npm APIs are imperative tools:
they do not persist application declarations, and their changes are lost on sync.

Version ranges reconstruct the requirements, but can resolve to newer releases.
For an identical dependency tree, preserve a matching npm lockfile separately,
restore it to `.node/package-lock.json`, generate the manifest with `sync()`
(which runs npm install), and use `ci()` for subsequent locked installs. npm owns
lockfile consistency and transitive resolution. No npm operation runs at startup.

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
For imperative workflows, preserve the manifest and lockfile for locked builds.
For declarative workflows, the manifest is generated and the lockfile must be
preserved separately if exact dependency-tree reproducibility is needed.

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
flask --app your_app node sync
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
configuration, asset selection, rendering, and build/watch commands. Flask serves
published assets through its configured static route.
Flask-Node declares/installs dependencies, executes commands, locates package
files, and publishes explicitly selected assets.

Package lookup supports ordinary and scoped registry names. Asset lookup returns
an existing `Path`; absolute paths, parent traversal, Windows-style paths, and
symlinks escaping the package or managed environment are rejected. Externally
linked packages are intentionally unsupported. Missing or malformed installed
packages raise `PackageNotFoundError`; unsafe or missing assets raise
`AssetResolutionError`. This is filesystem path validation, not protection
against concurrent malicious filesystem changes.

## Installed package entries

After packages have been installed explicitly, consumers can resolve their
JavaScript entry points through either the manager or the `Node` facade:

```python
entry = manager.resolve_entry("example")
plugin = manager.resolve_entry("example", "plugin")
scoped_entry = manager.resolve_entry("@scope/plugin")
# Equivalent, inside the current application's context:
entry = node.resolve_entry("example")
```

`resolve_entry(name, subpath=None)` returns an absolute, existing regular-file
`pathlib.Path`. Package and subpath are separate arguments; do not put a subpath
in `name`. Only locally installed packages under the manager's `node_modules`
are accepted. Resolution is anchored to that manager, independent of the Python
process's working directory or the location of consumer-owned source files.
It does not require or generate a managed project manifest.

The resolver invokes the configured `NODE_BIN` through `CommandRunner` and uses
Node's `module.createRequire(...).resolve(...)`. It never loads or evaluates the
target package, installs packages, invokes npm/npx, downloads files, copies
assets, or writes helper files. Invoke it during an explicit consumer operation
after installation; Flask-Node does not resolve entries or run processes during
normal Flask initialization.

Resolution follows Node's **require** semantics:

- `exports`, when present, takes precedence over `main` and controls which root
  and subpath entries are accessible. Blocked/private subpaths fail even when a
  matching file exists.
- Conditional exports use Node's active require conditions, including `node`,
  `require`, and applicable `default` branches, in manifest order. An
  `import`-only entry is unavailable. Additional conditions supplied by the Node
  runtime/configuration, such as version-dependent `module-sync`, follow Node's
  own behavior; Flask-Node does not emulate or override them.
- Without `exports`, Node uses `main` and its legacy file/directory lookup,
  including `.js`, `.json`, `.node` extension probing and index fallbacks.
  Export targets require their exact files; legacy extension/index probing does
  not apply to those targets. Nonstandard fields such as `module` are not used.

These semantics suit consumers using require-style JavaScript plugin resolution.
Consumers needing import-condition selection must not assume this API selects
that branch. Resolution is separate from loading: a returned path may identify
ESM, JSON, or a native addon, and does not guarantee that a consumer's loader can
execute it. See Node's [resolution documentation](https://nodejs.org/api/modules.html#requireresolverequest-options)
and [conditional exports](https://nodejs.org/api/packages.html#conditional-exports).

Package names use the existing registry-name validation. A supplied subpath must
be a nonempty relative string with no empty, `.` or `..` segments, absolute or
Windows drive paths, backslashes, NULs, or percent encoding. The package,
`node_modules`, and package manifest follow the existing symlink containment
checks. The resolved entry must remain within that installed package's resolved
root; internal symlinks are allowed, escaping symlinks are rejected. Ancestor or
global packages, built-ins, directories, and other non-file results are
unsupported. These are filesystem checks, not protection against concurrent
malicious filesystem changes.

Invalid package names raise `ConfigurationError`; missing or malformed installed
packages raise `PackageNotFoundError`; package containment failures retain
`AssetResolutionError`. Entry validation, Node resolution failures, and invalid
results raise the publicly exported `EntryResolutionError`, derived from
`NodeError`, with the requested entry and Node error code/message where available.
Missing Node and runner failures propagate as `ExecutableNotFoundError` and
`CommandExecutionError`; command diagnostics remain intact. Invalid resolver
responses include captured output in the error. Existing `resolve(name, asset)`
continues to resolve explicit filesystem paths and does not consult `exports`.

Package-entry resolution is available starting with **0.2.0**. Consumer
extensions using this API should declare `Flask-Node>=0.2.0`.

## Publishing browser assets

Consuming extensions choose which npm dependencies and browser assets they need.
During their `init_app()`, after Flask-Node is initialized, they can register:

```python
manager = node.get_manager(app)
manager.require("some-package", version="^1")
asset = manager.register_asset(
    package="some-package",
    source="dist/library.js",
    destination="vendor/library/library.js",
)
manager.register_asset(
    package="some-package",
    source="dist/images",
    destination="vendor/library/images",
)
```

Registration validates declarations and records them on the application's
manager. It does not copy files, require installed packages, change the manifest,
or run npm. Requirements and assets are registered separately. `manager.assets`
and `node.assets` expose a sorted tuple of immutable `NodeAsset` declarations.
Identical registrations deduplicate; different sources targeting the same
normalized destination or overlapping parent/child destinations raise
`AssetConflictError`.

Reconstruct the environment and publish explicitly:

```bash
pip install -e .
flask --app your_app node sync
flask --app your_app node publish
```

This copies selected files from `.node/node_modules/` into Flask's actual
configured `static_folder`. The CLI reports each package, source, destination,
and the total count. `sync` does not publish. Publishing does not run npm.
The default result above is `static/vendor/library/library.js` and a recursive
copy of the images directory. Custom Flask static folders are supported; static
serving disabled with `static_folder=None` produces a clear publication error.
A missing static directory is created during publication.

Python callers can use `manager.publish_assets()` / `node.publish_assets()` to
publish registrations and receive a tuple of destination `Path` objects.
`publish_asset(package, source, destination)` immediately publishes one asset
without registering it and returns its destination `Path`.

Files are replaced; registered directories are replaced completely, removing
stale files. Unrelated static files are preserved. File/directory type mismatches
fail clearly. Sources and destinations are preflighted before any batch copy;
copies are staged beside each destination and the previous destination is
restored if the final rename fails. A batch is not transactional: earlier assets
may already be updated if a later filesystem operation fails.

Sources resolve through the existing installed-package API. Absolute paths,
parent traversal, Windows drive paths, empty/root paths, and backslashes are
rejected. Resolved destinations must remain within the configured static root.
Directory source trees reject symlinks and special files; destination paths and
existing destination trees reject symlinks below the static root. The configured
static folder's resolved path defines that root. Source/destination overlap is
rejected. These checks do not protect against concurrent malicious filesystem
changes. Missing packages/assets and publication failures raise Flask-Node
errors, including `AssetPublicationError` for filesystem copy failures.

Consumers can use the registered static filename with Flask:

```python
from flask import url_for

url = url_for("static", filename=asset.destination)
```

HTML/Jinja rendering stays with the consuming extension. Flask-Node has no
library-specific asset selection, bundling, or rendering behavior.

Both `.node/` and registered `static/vendor/` destinations are generated,
reconstructable state. Applications can generally ignore them in Git, while
committing application source, Python dependencies, and `pyproject.toml`.
Flask-Node does not edit `.gitignore`. Exact dependency-tree reconstruction still
requires preserving a matching npm lockfile as described above.

## Development

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]' build
.venv/bin/python -m pytest
.venv/bin/python -m build
```

Tests inject/mock the runner and subprocess boundary. They never download npm
packages. Offline integration tests use temporary fake packages and real Node
when available; pytest reports explicit skips when Node is unavailable. A custom runner can be supplied to `Node(runner=...)`
or `NodeManager(..., runner=...)` for testing. This dependency injection is not a
consumer plugin protocol.

Inspired by [Flask-Tailwind-Manager](https://github.com/SebaSalinass/flask-tailwind-manager).
