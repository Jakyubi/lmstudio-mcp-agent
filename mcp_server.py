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
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_current_datetime":
        result = tools.get_current_datetime()
        return [TextContent(type="text", text=result)]
    raise ValueError(f"Unknown tool: {name}")

async def main():
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