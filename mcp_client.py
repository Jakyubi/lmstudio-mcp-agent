import asyncio
import logging
import threading
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool

logger = logging.getLogger(__name__)


class MCPClient:
    """Manages long-lived SSE transport and MCP session in a background daemon thread."""

    def __init__(self, sse_url: str = "http://127.0.0.1:8000/sse"):
        self.sse_url = sse_url
        self.loop = asyncio.new_event_loop()
        self.session: ClientSession | None = None
        self.tools: list[Tool] = []
        self.prompts: list[Any] = []

        self._ready = threading.Event()
        self._startup_error: Exception | None = None

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info(f"Connecting MCP client to {sse_url}...")
        if not self._ready.wait(timeout=15.0):
            raise TimeoutError("Timed out while connecting to MCP server.")
        if self._startup_error:
            raise self._startup_error
        logger.info("MCP Client initialized successfully.")

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._session_worker())

    async def _session_worker(self):
        """Establishing an SSE connection and keeping the MCP session alive."""
        self._close_event = asyncio.Event()
        try:
            async with sse_client(self.sse_url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    self.session = session
                    await self.session.initialize()

                    tools_response = await self.session.list_tools()
                    self.tools = tools_response.tools
                    logger.info(f"Loaded {len(self.tools)} tool(s) from MCP server.")

                    prompts_response = await self.session.list_prompts()
                    self.prompts = prompts_response.prompts
                    logger.info(
                        f"Loaded {len(self.prompts)} prompt(s) from MCP server."
                    )

                    self._ready.set()

                    await self._close_event.wait()

        except Exception as e:
            self._startup_error = e
            self._ready.set()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Thread-safe, synchronous tool invocation for Streamlit."""
        if not self.session:
            raise RuntimeError("MCP Session is not active.")

        async def _call():
            result = await self.session.call_tool(name, arguments)
            text_content = ""
            if result.content and len(result.content) > 0:
                text_content = result.content[0].text
            is_error = bool(result.isError)
            return text_content, is_error

        future = asyncio.run_coroutine_threadsafe(_call(), self.loop)
        return future.result(timeout=60.0)

    def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Fetches prompt content from the server."""
        if not self.session:
            raise RuntimeError("MCP Session is not active.")

        async def _get():
            res = await self.session.get_prompt(name, arguments or {})
            texts = [
                msg.content.text for msg in res.messages if hasattr(msg.content, "text")
            ]
            return "\n\n".join(texts).strip()

        future = asyncio.run_coroutine_threadsafe(_get(), self.loop)
        return future.result(timeout=15.0)

    def close(self):
        """Proper closure of the transport and event loop."""
        if self.loop.is_running() and hasattr(self, "_close_event"):
            self.loop.call_soon_threadsafe(self._close_event.set)
