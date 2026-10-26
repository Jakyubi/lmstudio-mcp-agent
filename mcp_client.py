import asyncio
import logging
import threading
from typing import Any, Dict, List

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool

logger = logging.getLogger(__name__)


class PersistentMCPClient:
    """Manages long-lived SSE transport and MCP session in a background daemon thread."""

    def __init__(self, sse_url: str = "http://127.0.0.1:8000/sse"):
        self.sse_url = sse_url
        self.loop = asyncio.new_event_loop()
        self.session: ClientSession | None = None
        self._sse_ctx = None
        self._session_ctx = None
        self.tools: List[Tool] = []

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info(f"Connecting persistent MCP client to {sse_url}...")
        future = asyncio.run_coroutine_threadsafe(self._connect(), self.loop)
        future.result(timeout=15.0)
        logger.info("Persistent MCP Client initialized successfully.")

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect(self):
        """Establishing an SSE connection and one-time MCP protocol negotiation."""
        self._sse_ctx = sse_client(self.sse_url)
        read_stream, write_stream = await self._sse_ctx.__aenter__()

        self._session_ctx = ClientSession(read_stream, write_stream)
        self.session = await self._session_ctx.__aenter__()

        await self.session.initialize()

        tools_response = await self.session.list_tools()
        self.tools = tools_response.tools
        logger.info(f"Loaded {len(self.tools)} tool(s) from MCP server.")

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> tuple[str, bool]:
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

    def list_prompts(self) -> List[Any]:
        """Pobiera listę dostępnych szablonów Prompt z serwera MCP."""
        if not self.session:
            return []

        async def _list():
            res = await self.session.list_prompts()
            return res.prompts

        future = asyncio.run_coroutine_threadsafe(_list(), self.loop)
        return future.result(timeout=10.0)

    def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> str:
        """Pobiera treść promptu z serwera i scala wiadomości w pojedynczy ciąg tekstowy."""
        if not self.session:
            raise RuntimeError("MCP Session is not active.")

        async def _get():
            res = await self.session.get_prompt(name, arguments or {})
            texts = []
            for msg in res.messages:
                content = msg.content
                if isinstance(content, str):
                    texts.append(content)
                elif hasattr(content, "text"):
                    texts.append(content.text)
                elif isinstance(content, list):
                    for block in content:
                        if hasattr(block, "text"):
                            texts.append(block.text)
                        elif isinstance(block, dict) and "text" in block:
                            texts.append(block["text"])
            return "\n\n".join(texts).strip()

        future = asyncio.run_coroutine_threadsafe(_get(), self.loop)
        return future.result(timeout=15.0)

    def close(self):
        """Proper closure of the transport and event loop."""

        async def _shutdown():
            if self._session_ctx:
                await self._session_ctx.__aexit__(None, None, None)
            if self._sse_ctx:
                await self._sse_ctx.__aexit__(None, None, None)

        if self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
            future.result(timeout=5.0)
            self.loop.call_soon_threadsafe(self.loop.stop)
