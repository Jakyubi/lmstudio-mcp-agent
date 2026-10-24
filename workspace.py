import logging
import os
import shlex
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
    def _verify_path(
        cls, current_ws: Path, raw_val: any, allow_empty: bool = False
    ) -> Path:
        """
        Weryfikuje i rozwiązuje pojedynczą ścieżkę.
        Chroni przed Path Traversal oraz bezpośrednim dostępem do .git.
        """
        raw_str = str(raw_val).strip() if raw_val is not None else ""

        if not raw_str:
            if allow_empty:
                return current_ws
            raise ValueError("Ścieżka nie może być pusta.")

        raw_path = Path(raw_str)
        resolved = (
            (current_ws / raw_path).resolve()
            if not raw_path.is_absolute()
            else raw_path.resolve()
        )

        try:
            resolved.relative_to(current_ws)
        except ValueError:
            raise PermissionError(
                f"Access Denied: Path '{raw_str}' tries to go out of: {current_ws}"
            )

        git_dir = current_ws / ".git"
        if resolved == git_dir or git_dir in resolved.parents:
            raise PermissionError("Access Denied: Direct access to .git is prohibited.")

        return resolved

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
                allow_empty = key in {"path", "repo_path"}
                resolved = cls._verify_path(
                    current_ws, sanitized[key], allow_empty=allow_empty
                )
                sanitized[key] = str(resolved)

        if "files_to_add" in sanitized and sanitized["files_to_add"] is not None:
            raw_files = str(sanitized["files_to_add"]).strip()
            if not raw_files or raw_files == ".":
                sanitized["files_to_add"] = "."
            else:
                try:
                    targets = shlex.split(raw_files, posix=(os.name != "nt"))
                    targets = [t.strip("\"'") for t in targets if t.strip()]
                except ValueError:
                    targets = raw_files.split()

                cleaned_targets = []
                for target in targets:
                    if target.startswith("-"):
                        raise ValueError(
                            f"Access Denied: Flag '{target}' is not allowed in file paths."
                        )

                    if target == ".":
                        cleaned_targets.append(".")
                        continue

                    resolved_target = cls._verify_path(
                        current_ws, target, allow_empty=False
                    )
                    rel_target = resolved_target.relative_to(current_ws)
                    cleaned_targets.append(str(rel_target).replace("\\", "/"))

                sanitized["files_to_add"] = (
                    " ".join(cleaned_targets) if cleaned_targets else "."
                )

        return sanitized
