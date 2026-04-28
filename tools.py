import os
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

def get_current_datetime():
    """Returns current date and time"""
    logging.debug("get_current_datetime called")
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def list_directory(path: str):
    """Lists the contents of a specified directory"""
    logging.debug("list_directory called")
    
    if not os.path.exists(path):
        return f"Error: Path '{path}' does not exist."
    if not os.path.isdir(path):
        return f"Error: Path '{path}' is not a folder."
    
    try:
        items = os.listdir(path)
        if not items:
            return f"'{path}' is empty."
        
        result=[f"Folder '{path}' contains:"]
        for item in items:
            full_path=os.path.join(path,item)
            item_type="[DIR]" if os.path.isdir(full_path) else "[FILE]"
            result.append(f"- {item_type} {item}")

        return "\n".join(result)
    except Exception as e:
        return f"Error reading folder: {str(e)}"
    
def read_file(file_path: str):
    """Reads the content of text file."""
    logging.debug("read_file called")
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' doesn't exist."
    if not os.path.isfile(file_path):
        return f"Error: Path '{file_path}' is not a file."
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                return f"File '{file_path}' is empty"
            return f"--- Beginning of file {file_path} ---\n{content}\n--- End of file ---"
    except UnicodeDecodeError:
        return f"Error: File '{file_path}' is probably a binary file, not text file."
    except Exception as e:
        return f"Error reading file: {str(e)}"
    
def get_git_diff(repo_path: str="."):
    """Returns the differences in uncommitted code in a given repository"""
    logging.debug("get_git_diff called")
    if not os.path.exists(repo_path):
        return f"Error: Path '{repo_path}' does not exist."
    if not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a folder."
    
    try:
        # Execute 'git diff' command as a subprocess without user interaction
        result = subprocess.run(
            ['git', 'diff'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10
        )
        diff_output=result.stdout.strip()

        if not diff_output:
            return f"--- Result of git diff for {repo_path} ---\nNo changes\n--- End ---"
        return f"--- Result of git diff for {repo_path} ---\n{diff_output}\n--- End ---"
    
    except subprocess.TimeoutExpired:
        return "Error: Git Diff exceeded time limit."
    except subprocess.CalledProcessError as e:
        return f"Git error: {e.stderr.strip()}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Check git installation."
    except Exception as e:
        return f"Error: {str(e)}"
    
def git_commit(repo_path: str, message: str, files_to_add: str="."):
    """Adds files to the staging area and creates a new commit"""
    logging.debug("git_commit called")
    if not os.path.exists(repo_path):
        return f"Error: Path '{repo_path}' does not exist."
    if not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a folder."
    
    try:
        # Phase 1: git add
        subprocess.run(
            ['git', 'add', files_to_add],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10
        )

        # Phase 2: git commit
        commit_result= subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=10
        )

        return f"--- Commit successful ---\n{commit_result.stdout.strip()}\n--- End ---"
    
    except subprocess.TimeoutExpired:
        return "Error: Git operations exceeded time limit."
    except subprocess.CalledProcessError as e:
        output= e.stdout.strip() if e.stdout else e.stderr.strip()
        return f"Git error: {output}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Check git installation."
    except Exception as e:
        return f"Error: {str(e)}"
    


def git_push(repo_path: str):
    """Pushes committed changes to the remote repository"""
    logging.debug("git_push called")
    if not os.path.exists(repo_path):
        return f"Error: Path '{repo_path}' does not exist."
    if not os.path.isdir(repo_path):
        return f"Error: Path '{repo_path}' is not a folder."
    
    try:
        push_result= subprocess.run(
            ['git', 'push'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=20
        )
        output = push_result.stderr.strip() if push_result.stderr else push_result.stdout.strip()
        return f"--- Push successful ---\n{output}\n--- End ---"
    
    except subprocess.TimeoutExpired:
        return "Error: Git push exceeded time limit."
    except subprocess.CalledProcessError as e:
        output= e.stdout.strip() if e.stdout else e.stderr.strip()
        return f"Git error: {output}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Check git installation."
    except Exception as e:
        return f"Error: {str(e)}"
    