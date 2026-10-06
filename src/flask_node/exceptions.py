"""Public exceptions raised by Flask-Node."""


class NodeError(Exception):
    """Base error for managed Node operations."""


class ConfigurationError(NodeError):
    pass


class EnvironmentError(NodeError):
    pass


class ExecutableNotFoundError(NodeError):
    pass


class CommandExecutionError(NodeError):
    def __init__(
        self,
        message: str,
        *,
        args: tuple[str, ...],
        cwd: str,
        returncode: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ):
        super().__init__(message)
        self.command = args
        self.cwd = cwd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class DependencyConflictError(NodeError):
    pass


class PackageNotFoundError(NodeError):
    pass


class AssetResolutionError(NodeError):
    pass
