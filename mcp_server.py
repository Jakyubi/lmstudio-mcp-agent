import logging

import uvicorn
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

import tools

# Logging configuration
logging.basicConfig(
    filename="mcp_server_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s - [MCP] - %(levelname)s - %(message)s",
    encoding="utf-8",
)

server = Server("mcp-server")

# Map linking tool names to functions from tools.py
TOOLS_MAP = {
    "get_current_datetime": tools.get_current_datetime,
    "list_directory": tools.list_directory,
    "read_file": tools.read_file,
    "write_file": tools.write_file,
    "git_status": tools.git_status,
    "get_git_diff": tools.get_git_diff,
    "git_commit": tools.git_commit,
    "git_push": tools.git_push,
    "git_pull": tools.git_pull,
    "git_undo_last_commit": tools.git_undo_last_commit,
}


@server.list_tools()
async def list_tools():
    """Defines tool schemas (name, description, arguments)"""
    return [
        Tool(
            name="get_current_datetime",
            description="Returns current date and time.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_directory",
            description="Lists all files and subdirectories in a given path. This is your PRIMARY tool for exploring "
            "the file system. Use this tool BEFORE assuming a file or folder exists. NEVER guess or "
            "hallucinate directory names. If you are searching for something, start by listing the root "
            "or parent directory to verify the actual structure.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to a folder you want to check. Use '.' for current directory.",
                    }
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="read_file",
            description="Reads text file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Exact path to a file you want to read.",
                    }
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="write_file",
            description="Creates a new file or completely overwrites an existing file with the specified content. "
            "When modifying an existing file, make sure you have read it first with read_file "
            "and provide the complete modified content here.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to create or overwrite (e.g. 'main.py' or 'src/utils.py').",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text/code to be written into the file.",
                    },
                },
                "required": ["file_path", "content"],
            },
        ),
        Tool(
            name="git_status",
            description="Returns an overview of changes in the repository (modified, staged, untracked files). "
            "Use this tool FIRST when asked about repository state, commits, or code reviews to identify "
            "which files were modified before fetching a full diff.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to Git repository. Use '.' for current directory.",
                    }
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="get_git_diff",
            description="Gets detailed code differences. Use this tool when a user asks to do a code review, check what they changed or find a bug in uncommitted code. The tool returns the exact code that was added or removed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to Git repository.",
                    }
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="git_commit",
            description="Stages files and creates a new Git commit. Only use this tool if the user asks you to commit changes to git. Always use a clear, descriptive commit message based on actual changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to Git repository. Use '.' for current directory.",
                    },
                    "message": {
                        "type": "string",
                        "description": "The commit message explaining changes.",
                    },
                    "files_to_add": {
                        "type": "string",
                        "description": "Space-separated list of files to stage before committing (e.g. 'file1.html file2.html') or '.' to stage all changes.",
                    },
                },
                "required": ["repo_path", "message"],
            },
        ),
        Tool(
            name="git_push",
            description="Pushes committed local changes to the remote repository. Only use when user asks you to push changes to GitHub.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to Git repository.",
                    }
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="git_pull",
            description="Pulls changes from the remote repository to synchronize local branch with remote before pushing. Use when remote changes need to be fetched.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to Git repository. Use '.' for current directory.",
                    }
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="git_undo_last_commit",
            description="Undoes the most recent local commit while keeping all changes in the files. Use this ONLY when the user explicitly requests to undo or revert the last commit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to Git repository. Use '.' for current directory.",
                    }
                },
                "required": ["repo_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Receives a tool execution request from the client, maps it, and executes the function"""
    logging.info(f"\n\nReceived tool call request: {name}")
    logging.debug(f"Arguments for {name}: {arguments}")

    if name not in TOOLS_MAP:
        logging.error(f"Requested unknown tool: {name}")
        raise ValueError(f"Unknown tool: {name}")
    try:
        handler = TOOLS_MAP[name]
        result = handler(**arguments)
        logging.info(f"Tool {name} executed successfully.")
        logging.debug(f"Tool {name} result: {result}")
        return [TextContent(type="text", text=str(result))]
    except Exception as e:
        logging.exception(f"Error executing tool: {name}")
        return [TextContent(type="text", text=f"Tool Execution Error: {str(e)}")]


sse = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    """Handles SSE stream connection"""
    async with sse.connect_sse(request.scope, request.receive, request._send) as (
        read_stream,
        write_stream,
    ):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
    return Response()


starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ]
)

if __name__ == "__main__":
    logging.info("Starting MCP server.")
    uvicorn.run(starlette_app, host="127.0.0.1", port=8000)
