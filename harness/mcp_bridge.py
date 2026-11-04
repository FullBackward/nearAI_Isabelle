"""mcp_bridge.py - a synchronous handle on one MCP stdio server.

agentlib's loop is synchronous (it blocks on the model's stream), the MCP SDK
is asyncio. This runs the SDK on a private thread with its own event loop and
exposes `list_tools()` / `call(name, args, timeout)` as plain blocking calls.
One bridge = one MCP server process = one Isabelle session on the Pool Server
(the LSP MCP binds the problem file to a session on first use).
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Optional


class MCPBridge:
    def __init__(self, command: list[str], env: dict[str, str] | None = None,
                 cwd: str | None = None, startup_timeout: float = 60.0):
        self.command = command
        self.env = {**os.environ, **(env or {})}
        self.cwd = cwd
        self.startup_timeout = startup_timeout
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True,
                                        name="mcp-bridge")
        self._ready = threading.Event()
        self._stop: Optional[asyncio.Event] = None
        self._session = None
        self._error: Optional[BaseException] = None
        self._main_task = None
        self.instructions: Optional[str] = None

    # -- lifecycle --------------------------------------------------------- #
    def start(self) -> "MCPBridge":
        self._thread.start()
        self._main_task = asyncio.run_coroutine_threadsafe(self._main(), self._loop)
        if not self._ready.wait(self.startup_timeout):
            self.close()
            raise RuntimeError(f"MCP server did not come up in {self.startup_timeout}s: {self.command}")
        if self._error is not None:
            err = self._error
            self.close()
            raise RuntimeError(f"MCP server failed to start: {type(err).__name__}: {err}")
        return self

    async def _main(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        self._stop = asyncio.Event()
        params = StdioServerParameters(command=self.command[0], args=self.command[1:],
                                       env=self.env, cwd=self.cwd)
        try:
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as session:
                    init = await session.initialize()
                    self.instructions = getattr(init, "instructions", None)
                    self._session = session
                    self._ready.set()
                    await self._stop.wait()
        except BaseException as e:                     # noqa: BLE001
            self._error = e
            self._ready.set()
        finally:
            self._session = None

    def close(self) -> None:
        if self._stop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop.set)
            if self._main_task is not None:
                try:
                    self._main_task.result(timeout=15)
                except BaseException:                  # noqa: BLE001
                    pass
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.close()

    # -- calls ------------------------------------------------------------- #
    def _run(self, coro, timeout: float):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return fut.result(timeout=timeout)
        except TimeoutError:
            fut.cancel()
            raise

    def list_tools(self) -> list[dict[str, Any]]:
        async def _lt():
            res = await self._session.list_tools()
            return [{"name": t.name, "description": t.description or "",
                     "parameters": t.inputSchema} for t in res.tools]
        return self._run(_lt(), 60)

    def call(self, name: str, arguments: dict[str, Any], timeout: float = 300.0) -> str:
        """The tool's text output. MCP-level errors come back as text that
        starts with `MCP tool error`, timeouts as `Tool call timed out`; the
        agent loop is never interrupted by a tool."""
        async def _ct():
            res = await self._session.call_tool(name, arguments)
            parts = [c.text for c in res.content if getattr(c, "type", "") == "text"]
            text = "\n".join(parts) or "(no output)"
            if getattr(res, "isError", False):
                return f"MCP tool error ({name}): {text}"
            return text
        try:
            return self._run(_ct(), timeout)
        except TimeoutError:
            return f"Tool call timed out after {timeout:.0f}s ({name}). The server may still be busy; try a smaller step."
        except Exception as e:                           # noqa: BLE001
            return f"MCP tool error ({name}): {type(e).__name__}: {e}"

    def call_json(self, name: str, arguments: dict[str, Any], timeout: float = 300.0) -> Any:
        out = self.call(name, arguments, timeout)
        try:
            return json.loads(out)
        except (TypeError, ValueError):
            return {"raw": out}
