import logging
from typing import Annotated

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

import tools
from workspace import WorkspaceManager

# Logging configuration
logging.basicConfig(
    filename="mcp_server_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s - [MCP] - %(levelname)s - %(message)s",
    encoding="utf-8",
)

logger = logging.getLogger(__name__)


mcp = FastMCP("mcp-server")


@mcp.tool(
    name="get_current_datetime",
    description="Returns current date and time.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def get_current_datetime() -> str:
    return tools.get_current_datetime()


@mcp.tool(
    name="list_directory",
    description=(
        "Lists all files and subdirectories in a given path. This is your PRIMARY tool for exploring "
        "the file system. Use this tool BEFORE assuming a file or folder exists. NEVER guess or "
        "hallucinate directory names. If you are searching for something, start by listing the root "
        "or parent directory to verify the actual structure."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def list_directory(
    path: Annotated[
        str,
        Field(
            default=".",
            description="Path to a folder you want to check. Use '.' for current directory.",
        ),
    ] = ".",
    max_depth: Annotated[
        int,
        Field(
            default=2,
            description="How many levels deep to scan (1 to 5). Default is 2.",
        ),
    ] = 2,
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"path": path})
    # Ograniczenie wartości max_depth w granicach rozsądku (1-5), by chronić tokeny
    safe_depth = max(1, min(max_depth, 5))
    return tools.list_directory(path=safe_args["path"], max_depth=safe_depth)


@mcp.tool(
    name="read_file",
    description="Reads text file",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def read_file(
    file_path: Annotated[
        str, Field(description="Exact path to a file you want to read.")
    ],
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"file_path": file_path})
    return tools.read_file(**safe_args)


@mcp.tool(
    name="write_file",
    description=(
        "Creates a new file or completely overwrites an existing file with the specified content. "
        "When modifying an existing file, make sure you have read it first with read_file "
        "and provide the complete modified content here."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def write_file(
    file_path: Annotated[
        str,
        Field(
            description="Path to the file to create or overwrite (e.g. 'main.py' or 'src/utils.py')."
        ),
    ],
    content: Annotated[
        str,
        Field(
            description="The full text/code to be written into the file.",
        ),
    ],
) -> str:
    safe_args = WorkspaceManager.guard_arguments(
        {"file_path": file_path, "content": content}
    )
    return tools.write_file(**safe_args)


@mcp.tool(
    name="delete_file",
    description=(
        "Deletes a specified file from the filesystem. "
        "ONLY use this tool if the user explicitly asks to delete, remove, or trash a file. "
        "Never delete files automatically without a clear user request."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def delete_file(
    file_path: Annotated[
        str, Field(description="Exact path to the file you want to delete.")
    ],
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"file_path": file_path})
    return tools.delete_file(**safe_args)


@mcp.tool(
    name="rename_file",
    description=(
        "Renames a specified file. Will automaticly create missing folders if needed"
        "ONLY use this tool if the user explicitly asks to rename, or move file to other folder. "
        "Never rename files automatically without a clear user request."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def rename_file(
    old_path: Annotated[str, Field(description="Original path to the file.")],
    new_path: Annotated[str, Field(description="New path to the file.")],
) -> str:
    safe_args = WorkspaceManager.guard_arguments(
        {"old_path": old_path, "new_path": new_path}
    )
    return tools.rename_file(**safe_args)


@mcp.tool(
    name="git_status",
    description=(
        "Returns an overview of changes in the repository (modified, staged, untracked files). "
        "Use this tool FIRST when asked about repository state, commits, or code reviews to identify "
        "which files were modified before fetching a full diff."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def git_status(
    repo_path: Annotated[
        str,
        Field(
            default=".",
            description="Path to Git repository. Use '.' for current directory.",
        ),
    ] = ".",
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"repo_path": repo_path})
    return tools.git_status(**safe_args)


@mcp.tool(
    name="get_git_diff",
    description=(
        "Gets detailed code differences. Use this tool when a user asks to do a code review, "
        "check what they changed or find a bug in uncommitted code. The tool returns the exact code "
        "that was added or removed."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def get_git_diff(
    repo_path: Annotated[
        str,
        Field(
            default=".",
            description="Path to Git repository. Use '.' for current directory.",
        ),
    ] = ".",
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"repo_path": repo_path})
    return tools.get_git_diff(**safe_args)


@mcp.tool(
    name="git_commit",
    description=(
        "Stages files and creates a new Git commit. Only use this tool if the user asks you to commit changes to git. "
        "Always use a clear, descriptive commit message based on actual changes."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def git_commit(
    message: Annotated[
        str, Field(description="The commit message explaining changes.")
    ],
    repo_path: Annotated[
        str,
        Field(
            default=".",
            description="Path to Git repository. Use '.' for current directory.",
        ),
    ] = ".",
    files_to_add: Annotated[
        str,
        Field(
            default=".",
            description="Space-separated list of files to stage before committing (e.g. 'file1.html file2.html') or '.' to stage all changes.",
        ),
    ] = ".",
) -> str:
    safe_args = WorkspaceManager.guard_arguments(
        {
            "repo_path": repo_path,
            "message": message,
            "files_to_add": files_to_add,
        }
    )
    return tools.git_commit(**safe_args)


@mcp.tool(
    name="git_push",
    description="Pushes committed local changes to the remote repository. Only use when user asks you to push changes to GitHub.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def git_push(
    repo_path: Annotated[
        str,
        Field(
            default=".",
            description="Path to Git repository. Use '.' for current directory.",
        ),
    ] = ".",
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"repo_path": repo_path})
    return tools.git_push(**safe_args)


@mcp.tool(
    name="git_pull",
    description="Pulls changes from the remote repository to synchronize local branch with remote before pushing. Use when remote changes need to be fetched.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def git_pull(
    repo_path: Annotated[
        str,
        Field(
            default=".",
            description="Path to Git repository. Use '.' for current directory.",
        ),
    ] = ".",
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"repo_path": repo_path})
    return tools.git_pull(**safe_args)


@mcp.tool(
    name="git_undo_last_commit",
    description="Undoes the most recent local commit while keeping all changes in the files. Use this ONLY when the user explicitly requests to undo or revert the last commit.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def git_undo_last_commit(
    repo_path: Annotated[
        str,
        Field(
            default=".",
            description="Path to Git repository. Use '.' for current directory.",
        ),
    ] = ".",
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"repo_path": repo_path})
    return tools.git_undo_last_commit(**safe_args)


@mcp.prompt(
    name="prepare_conventional_commit",
    description="Inspects diff and prepares a standardized Conventional Commit message.",
)
def prepare_conventional_commit() -> str:
    return (
        "Your task is to prepare a professional commit message following the Conventional Commits specification.\n\n"
        "Execute EXACTLY these steps in sequence:\n"
        "1. Call `git_status` to verify if there are any modified or staged files. "
        "If the working tree is clean, inform the user and stop.\n"
        "2. Call `get_git_diff` to fetch all uncommitted changes.\n"
        "3. Analyze the diff to understand the main intent behind the changes (what was changed and why).\n"
        "4. Propose a concise commit title in the format: `<type>(<optional-scope>): <imperative summary>` "
        "(e.g., feat: add error handling, fix: prevent path traversal, refactor: streamline git calls).\n"
        "5. Provide 2-3 concise bullet points explaining key changes.\n"
        "6. Conclude by asking: 'Would you like me to commit these changes using git_commit?' "
        "Do NOT call `git_commit` without explicit user confirmation."
    )


@mcp.prompt(
    name="pre_commit_sanity_check",
    description="Pre-commit audit: checks for leftover debugging artifacts, secrets, and repository clutter.",
)
def pre_commit_sanity_check() -> str:
    return (
        "Perform a pre-commit code hygiene and sanity audit. Follow these steps in sequence:\n\n"
        "1. Call `git_status` to inspect modified and untracked files.\n"
        "2. Check untracked files for artifacts that should NOT be committed (e.g., *.log files, *.env secrets, temp files). "
        "Warn the user explicitly if any suspicious files are found.\n"
        "3. Call `get_git_diff` to inspect modified code lines.\n"
        "4. Scan the diff for leftover debugging artifacts:\n"
        "   - Print/logging statements: print(), console.log(), breakpoint(), pdb, debugger;\n"
        "   - Large blocks of commented-out, dead code.\n"
        "5. Output a clean, structured checklist:\n"
        "   - [ ] Repository Hygiene (Staged files vs untracked clutter)\n"
        "   - [ ] Leftover Debug / Dead Code (Specify file and line, or state 'Clean')\n"
        "   - [ ] Summary (2 sentences explaining what this change actually does)."
    )


@mcp.tool(
    name="search_code",
    description=(
        "Searches for a text pattern, keyword, or function name across project files. "
        "Use this tool to locate where code is defined or referenced without reading files one by one."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def search_code(
    query: Annotated[
        str,
        Field(
            description="The text or pattern to search for (e.g. 'def handle_click', 'TODO', 'DB_URL')."
        ),
    ],
    path: Annotated[
        str,
        Field(
            default=".",
            description="Directory to search in. Use '.' for current workspace.",
        ),
    ] = ".",
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"path": path})
    return tools.search_code(query=query, **safe_args)


@mcp.tool(
    name="get_recent_commits",
    description="Returns a brief list of the most recent Git commits (hash, date, title). Use this to check recent history, summarize work, or prepare standup notes.",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def get_recent_commits(
    count: Annotated[
        int,
        Field(
            default=5,
            description="Number of recent commits to fetch (1 to 20). Default is 5.",
        ),
    ] = 5,
    repo_path: Annotated[
        str,
        Field(
            default=".",
            description="Path to Git repository. Use '.' for current directory.",
        ),
    ] = ".",
) -> str:
    safe_args = WorkspaceManager.guard_arguments({"repo_path": repo_path})
    return tools.get_recent_commits(repo_path=safe_args["repo_path"], count=count)


# Utworzenie aplikacji Starlette z trasami /sse oraz /messages/
app = mcp.sse_app()

if __name__ == "__main__":
    logger.info("Starting MCP server.")
    uvicorn.run(
        "mcp_server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_excludes=["*.log", ".workspace"],
    )
