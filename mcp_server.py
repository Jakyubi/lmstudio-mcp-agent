import asyncio
import logging

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import tools

logging.basicConfig(
    filename="mcp_server_debug.log",
    level=logging.DEBUG,
    format='%(asctime)s - [MCP] - %(levelname)s - %(message)s',
    encoding='utf-8'
)

server = Server("mcp-server")

TOOLS_MAP = {
    "get_current_datetime": tools.get_current_datetime,
    "list_directory": tools.list_directory
}

@server.list_tools()
async def list_tools():
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
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
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