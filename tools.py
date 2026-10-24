import logging
import os
import shlex
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def get_current_datetime():
    """Returns current date and time"""
    logger.debug("get_current_datetime called")
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_directory(path: str):
    """Lists the contents of a specified directory"""
    logger.debug("list_directory called")

    if not os.path.exists(path):
        return f"Error: Path '{path}' does not exist."
    if not os.path.isdir(path):
        return f"Error: Path '{path}' is not a folder."

    try:
        items = os.listdir(path)
        if not items:
            return f"'{path}' is empty."

        result = [f"Folder '{path}' contains:"]
        for item in items:
            full_path = os.path.join(path, item)
            item_type = "[DIR]" if os.path.isdir(full_path) else "[FILE]"
            result.append(f"- {item_type} {item}")

        return "\n".join(result)
    except Exception as e:
        return f"Error reading folder: {e}"


def read_file(file_path: str):
    """Reads the content of text file."""
    logger.debug("read_file called")
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' doesn't exist."
    if not os.path.isfile(file_path):
        return f"Error: Path '{file_path}' is not a file."

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip():
                return f"File '{file_path}' is empty"
            return (
                f"--- Beginning of file {file_path} ---\n{content}\n--- End of file ---"
            )
    except UnicodeDecodeError:
        return f"Error: File '{file_path}' is probably a binary file, not text file."
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(file_path: str, content: str):
    """Creates a new file or overwrites an existing file with the provided content."""
    logger.debug(f"write_file called for: {file_path}")

    if not file_path or not file_path.strip():
        return "Error: File path cannot be empty."

    if os.path.isdir(file_path):
        return f"Error: Path '{file_path}' is an existing directory, not a file."

    try:
        # Auto create missing folders
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Created missing directory tree: {directory}")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        file_size = len(content.encode("utf-8"))
        return f"--- File written successfully ---\nPath: {file_path}\nBytes written: {file_size}\n--- End ---"

    except Exception as e:
        logger.exception(f"Error writing to file {file_path}")
        return f"Error writing file: {e}"


def git_status(repo_path: str = "."):
    """Returns the current status of the Git repository (short format)"""
    logger.debug("git_status called")
    if not os.path.exists(repo_path):
        return f"Error: Path '{repo_path}' does not exist."
    if not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a folder."

    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
        output = result.stdout.strip()
        if not output:
            return f"--- Git status for {repo_path} ---\nWorking tree clean (no changes)\n--- End ---"
        return f"--- Git status for {repo_path} ---\n{output}\n--- End ---"

    except subprocess.TimeoutExpired:
        return "Error: Git status exceeded time limit."
    except subprocess.CalledProcessError as e:
        output = e.stdout.strip() if e.stdout else e.stderr.strip()
        return f"Git error: {output}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Check git installation."
    except Exception as e:
        return f"Error: {e}"


def get_git_diff(repo_path: str = "."):
    """Returns the differences in uncommitted code (staged, unstaged, and untracked files) in a given repository"""
    logger.debug("get_git_diff called")
    if not os.path.exists(repo_path):
        return f"Error: Path '{repo_path}' does not exist."
    if not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a folder."

    try:
        diff_parts = []

        # Check whether repo has commits
        has_head = (
            subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=5,
                check=False,
            ).returncode
            == 0
        )

        # Get diff
        diff_cmd = ["git", "diff", "HEAD"] if has_head else ["git", "diff", "--cached"]
        tracked_diff = subprocess.run(
            diff_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        ).stdout.strip()

        if not has_head:
            unstaged_diff = subprocess.run(
                ["git", "diff"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                stdin=subprocess.DEVNULL,
                timeout=10,
            ).stdout.strip()
            if unstaged_diff:
                tracked_diff = f"{tracked_diff}\n{unstaged_diff}".strip()

        if tracked_diff:
            diff_parts.append(tracked_diff)

        # Get new files list
        untracked_proc = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
        untracked_files = [
            f.strip() for f in untracked_proc.stdout.splitlines() if f.strip()
        ]

        # Get diff for each new file
        for file_rel_path in untracked_files:
            diff_new = subprocess.run(
                ["git", "diff", "--no-index", "--", "/dev/null", file_rel_path],
                cwd=repo_path,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if diff_new.stdout.strip():
                diff_parts.append(diff_new.stdout.strip())

        full_diff = "\n\n".join(diff_parts).strip()

        if not full_diff:
            return (
                f"--- Result of git diff for {repo_path} ---\nNo changes\n--- End ---"
            )
        return f"--- Result of git diff for {repo_path} ---\n{full_diff}\n--- End ---"

    except subprocess.TimeoutExpired:
        return "Error: Git Diff exceeded time limit."
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip() if e.stderr else str(e)
        return f"Git error: {err}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Check git installation."
    except Exception as e:
        return f"Error: {e}"


def git_commit(repo_path: str, message: str, files_to_add: str = "."):
    """Adds files to the staging area and creates a new commit"""
    logger.debug("git_commit called")
    if not os.path.exists(repo_path):
        return f"Error: Path '{repo_path}' does not exist."
    if not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a folder."

    try:
        raw_files = files_to_add.strip() if files_to_add else "."
        if raw_files == ".":
            targets = ["."]
        else:
            try:
                targets = shlex.split(raw_files, posix=(os.name != "nt"))
                targets = [t.strip("\"'") for t in targets if t.strip()]
            except ValueError:
                targets = raw_files.split()

        for t in targets:
            if t.startswith("-"):
                return f"Error: Flag '{t}' is not allowed in file targets."

        # Phase 1: git add
        subprocess.run(
            ["git", "add", "--"] + targets,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )

        # Phase 2: git commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )

        return f"--- Commit successful ---\n{commit_result.stdout.strip()}\n--- End ---"

    except subprocess.TimeoutExpired:
        return "Error: Git operations exceeded time limit."
    except subprocess.CalledProcessError as e:
        output = e.stdout.strip() if e.stdout else e.stderr.strip()
        return f"Git error: {output}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Check git installation."
    except Exception as e:
        return f"Error: {e}"


def git_push(repo_path: str):
    """Pushes committed changes to the remote repository"""
    logger.debug("git_push called")
    if not os.path.exists(repo_path):
        return f"Error: Path '{repo_path}' does not exist."
    if not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a folder."

    try:
        push_result = subprocess.run(
            ["git", "push"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=20,
        )
        output = (
            push_result.stderr.strip()
            if push_result.stderr
            else push_result.stdout.strip()
        )
        return f"--- Push successful ---\n{output}\n--- End ---"

    except subprocess.TimeoutExpired:
        return "Error: Git push exceeded time limit."
    except subprocess.CalledProcessError as e:
        output = e.stdout.strip() if e.stdout else e.stderr.strip()
        return f"Git error: {output}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Check git installation."
    except Exception as e:
        return f"Error: {e}"


def git_pull(repo_path: str = "."):
    """Pulls changes from the remote repository safely"""
    logger.debug("git_pull called")
    if not os.path.exists(repo_path):
        return f"Error: Path '{repo_path}' does not exist."
    if not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a folder."

    try:
        result = subprocess.run(
            ["git", "pull", "--no-rebase"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=20,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return f"--- Pull successful ---\n{output}\n--- End ---"

    except subprocess.CalledProcessError as e:
        error_output = (e.stdout + "\n" + e.stderr).strip()

        # In case of conflict take a step back
        if "conflict" in error_output.lower():
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=repo_path,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            return (
                f"Conflict detected during git pull! Merge was automatically aborted to preserve repository state. "
                f"Conflicting files need to be resolved manually by the developer.\nDetails:\n{error_output}"
            )

        return f"Git error: {error_output}"
    except subprocess.TimeoutExpired:
        return "Error: Git pull exceeded time limit."
    except Exception as e:
        return f"Error: {e}"


def git_undo_last_commit(repo_path: str = "."):
    """Undoes the last local commit while preserving all changes in the working directory (git reset HEAD~1)"""
    logger.debug("git_undo_last_commit called")
    if not os.path.exists(repo_path) or not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a valid directory."

    try:
        result = subprocess.run(
            ["git", "reset", "HEAD~1"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return f"--- Successfully undone last commit ---\n{output}\nAll file changes were kept as uncommitted."
    except subprocess.CalledProcessError as e:
        return f"Git error: {e.stderr.strip() or e.stdout.strip()}"
    except Exception as e:
        return f"Error: {e}"
