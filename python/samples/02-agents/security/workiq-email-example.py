from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import sys
from contextlib import AsyncExitStack, suppress
from pathlib import Path

from agent_framework import (
    Agent,
    MCPStreamableHTTPTool,
    ToolApprovalMiddleware,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework.security import SecureAgentConfig, SecureMCPToolProxy
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

FOUNDRY_MODEL = os.getenv("FOUNDRY_MODEL", "gpt-5")

AGENT_INSTRUCTIONS = (
    "Act as my high-autonomy productivity agent: read and respond to my emails/teams messages, "
    "infer intent, and complete tasks using available WorkIQ MCP server tools without asking "
    "unnecessary questions. Reply if you have to, do not ask me for confirmation."
)


async def run_devui_async(*, debug: bool = False, gateway_port: int = 9090) -> None:
    """Launch DevUI with the WorkIQ email MCP proxy."""
    import uvicorn
    from agent_framework_devui._server import DevServer

    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv()
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is required for FoundryChatClient.")

    credential = AzureCliCredential()
    main_client = FoundryChatClient(
        project_endpoint=endpoint,
        model=FOUNDRY_MODEL,
        credential=credential,
    )

    mail_url = f"http://localhost:{gateway_port}/mcp/WorkIQ-MailTools"

    async with AsyncExitStack() as stack:
        secure_mcp = await stack.enter_async_context(
            SecureMCPToolProxy(
                mcp_tool=MCPStreamableHTTPTool(
                    name="WorkIQ-MailServer",
                    url=mail_url,
                    description="WorkIQ Email MCP server via local proxy",
                    tool_name_prefix="mail",
                    terminate_on_close=False,
                    load_prompts=False,
                ),
                gateway_policy=True,
            )
        )
        print(f"Connected to MCP proxy: {mail_url}")
        print(f"Loaded tools (Email): {len(secure_mcp.tools)}")

        config = SecureAgentConfig(
            auto_hide_untrusted=False,
            enable_policy_enforcement=True,
            approval_on_violation=True,
            quarantine_chat_client=None,
        )

        agent = await stack.enter_async_context(
            Agent(
                client=main_client,
                name="WorkIQSecureAgent",
                instructions=AGENT_INSTRUCTIONS,
                tools=[secure_mcp],
                context_providers=[config],
                middleware=[ToolApprovalMiddleware()],
            )
        )

        host = "127.0.0.1"
        port = 8090
        auth_token = os.environ.get("DEVUI_AUTH_TOKEN") or secrets.token_urlsafe(32)

        server_obj = DevServer(
            port=port,
            host=host,
            auth_enabled=True,
            auth_token=auth_token,
        )
        server_obj.set_pending_entities([agent])
        app = server_obj.get_app()

        print("\n" + "=" * 70)
        print("DevUI: WorkIQ Email MCP + FIDES")
        print("=" * 70)
        print(f"URL:          http://{host}:{port}")
        print(f"Entity ID:    agent_{agent.name}")
        print(f"Bearer token: {auth_token}")
        print("\nPress Ctrl+C to stop.\n")

        uvicorn_config = uvicorn.Config(app, host=host, port=port, log_level="info")
        uvicorn_server = uvicorn.Server(uvicorn_config)
        with suppress(KeyboardInterrupt):
            await uvicorn_server.serve()


def _parse_args(argv: list[str]) -> tuple[bool, int]:
    """Parse CLI arguments. Returns (debug, gateway_port)."""
    parser = argparse.ArgumentParser(description="Run the WorkIQ Email MCP + FIDES DevUI sample.")
    parser.add_argument("--debug", action="store_true", help="Enable verbose security logging.")
    parser.add_argument(
        "--gateway-port",
        type=int,
        default=9090,
        help="Port of the local Fides gateway (default: 9090).",
    )
    args = parser.parse_args(argv)
    return args.debug, args.gateway_port


def main() -> None:
    """Entry point for the sample script."""
    debug, gateway_port = _parse_args(sys.argv[1:])
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("agent_framework.security").setLevel(logging.DEBUG if debug else logging.WARNING)
    try:
        asyncio.run(run_devui_async(debug=debug, gateway_port=gateway_port))
    except RuntimeError as ex:
        print(f"\nError: {ex}", file=sys.stderr)
        raise SystemExit(1) from ex
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)


if __name__ == "__main__":
    main()
