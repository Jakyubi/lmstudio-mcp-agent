import logging
from pathlib import Path

STATE_FILE = Path(".workspace")

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Handles active workspace and path isolation."""

    PATH_KEYS = frozenset({"path", "file_path", "repo_path"})

    @classmethod
    def get_workspace(cls) -> Path:
        """Gets active workspace"""
        if STATE_FILE.exists():
            try:
                saved = STATE_FILE.read_text(encoding="utf-8").strip()
                p = Path(saved).resolve()
                if p.is_dir():
                    return p
            except Exception as e:
                logger.debug(f"Couldn't read workspace state file: {e}")

        return Path.cwd().resolve()

    @classmethod
    def set_workspace(cls, new_path: str) -> Path:
        """Verify and save new workspace dir."""
        target = Path(new_path.strip()).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Path '{new_path}' does not exist.")
        if not target.is_dir():
            raise NotADirectoryError(f"Path '{new_path}' is not a folder.")

        STATE_FILE.write_text(str(target), encoding="utf-8")
        return target

    @classmethod
    def guard_arguments(cls, arguments: dict) -> dict:
        """
        Verifies tool arguments
        Returns dictionary with safe paths
        """
        current_ws = cls.get_workspace()
        sanitized = arguments.copy()

        for key in cls.PATH_KEYS:
            if key in sanitized:
                raw_val = sanitized[key]
                raw_path = Path(str(raw_val).strip() if raw_val else ".")

                resolved = (
                    (current_ws / raw_path).resolve()
                    if not raw_path.is_absolute()
                    else raw_path.resolve()
                )

                try:
                    resolved.relative_to(current_ws)
                except ValueError:
                    raise PermissionError(
                        f"Access Denied: Path '{raw_val}' tries to go out of: {current_ws}"
                    )

                git_dir = current_ws / ".git"
                if resolved == git_dir or git_dir in resolved.parents:
                    raise PermissionError(
                        "Access Denied: Direct access to .git is prohibited."
                    )

                sanitized[key] = str(resolved)

        return sanitized
