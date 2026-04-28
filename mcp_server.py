import asyncio
import logging

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import tools

# Logging configuration
logging.basicConfig(
    filename="mcp_server_debug.log",
    level=logging.DEBUG,
    format='%(asctime)s - [MCP] - %(levelname)s - %(message)s',
    encoding='utf-8'
)

server = Server("mcp-server")

# Map linking tool names to functions from tools.py
TOOLS_MAP = {
    "get_current_datetime": tools.get_current_datetime,
    "list_directory": tools.list_directory,
    "read_file": tools.read_file,
    "get_git_diff": tools.get_git_diff,
    "git_commit": tools.git_commit,
    "git_push": tools.git_push
}

@server.list_tools()
async def list_tools():
    """Defines tool schemas (name, description, arguments)"""
    return[
        Tool(
            name="get_current_datetime",
            description="Returns current date and time.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
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
                        "description": "Path to a folder you want to check. Use '.' for current directory."
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="read_file",
            description="Reads text file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path":{
                        "type": "string",
                        "description":"Exact path to a file you want to read."
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="get_git_diff",
            description="Gets detailed code differences. Use this tool when a user asks to do a code review, check what they changed or find a bug in uncommitted code. The tool returns the exact code that was added or removed.",
            inputSchema={
                "type": "object",
                "properties":{
                    "repo_path":{
                        "type": "string",
                        "description": "Path to Git repository."
                    }
                },
                "required": ["repo_path"]
            }
        ),
        Tool(
            name="git_commit",
            description="Stages files and creates a new Git commit. Only use this tool if the user asks you to commit changes to git. Always use a clear, descriptive commit message based on actual changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path":{
                        "type": "string",
                        "description": "Path to Git repository. Use '.' for current directory."
                    },
                    "message":{
                        "type": "string",
                        "description": "The commit message explaining changes."
                    },
                    "files_to_add":{
                        "type":"string",
                        "description": "Files to stage before commiting. Defaults to '.' (which stages all files). You can specify a single file path if the user requests it."
                    }
                },
                "required": ["repo_path", "message"]
            }
        ),
        Tool(
            name="git_push",
            description="Pushes committed local changes to the remote repository. Only use when user asks you to push changes to GitHub.",
            inputSchema={
                "type": "object",
                "properties":{
                    "repo_path":{
                        "type": "string",
                        "description": "Path to Git repository."
                    }
                },
                "required": ["repo_path"]
            }
        )
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

async def main():
    """Starts MCP server using standard I/O streams"""
    logging.info("Starting MCP server.")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())