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
    Message,
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


async def run_cli_async(*, debug: bool = False, gateway_port: int = 9090, auto_approve: bool = False) -> None:
    """Run the sample in CLI mode with two MCP proxies (WorkIQ email + teams)."""
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

    teams_url = f"http://localhost:{gateway_port}/mcp/WorkIQ-TeamsServer"
    mail_url = f"http://localhost:{gateway_port}/mcp/WorkIQ-MailTools"

    async with AsyncExitStack() as stack:
        secure_mcp_1 = await stack.enter_async_context(
            SecureMCPToolProxy(
                mcp_tool=MCPStreamableHTTPTool(
                    name="WorkIQ-TeamsServer",
                    url=teams_url,
                    description="WorkIQ Teams MCP server via local proxy",
                    tool_name_prefix="teams",
                ),
                gateway_policy=True,
            )
        )
        print(f"Connected to MCP proxy: {teams_url}")
        print(f"Loaded tools (Teams): {len(secure_mcp_1.tools)}")

        secure_mcp_2 = await stack.enter_async_context(
            SecureMCPToolProxy(
                mcp_tool=MCPStreamableHTTPTool(
                    name="WorkIQ-MailServer",
                    url=mail_url,
                    description="WorkIQ Email MCP server via local proxy",
                    tool_name_prefix="mail",
                ),
                gateway_policy=True,
            )
        )
        print(f"Connected to MCP proxy: {mail_url}")
        print(f"Loaded tools (Email): {len(secure_mcp_2.tools)}")

        all_tools = secure_mcp_1.tools + secure_mcp_2.tools

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
                tools=all_tools,
                context_providers=[config],
                middleware=[ToolApprovalMiddleware()],
            )
        )

        # ToolApprovalMiddleware requires an AgentSession so it can coordinate
        # (and queue) approval prompts across runs when parallel tool calls
        # each trigger a policy-violation approval.
        session = agent.create_session()

        query = "Handle my recent unread emails."
        print("\nUser:", query)

        # ToolApprovalMiddleware surfaces policy-violation approvals one batch at
        # a time (queuing parallel requests in session state). Each request is
        # resolved by prompting the user, unless --auto-approve was passed.
        result = await agent.run(query, session=session)
        while result.user_input_requests:
            approvals = []
            for req in result.user_input_requests:
                function_call = req.function_call
                tool_name = function_call.name if function_call is not None else "<unknown>"
                if auto_approve:
                    approved = True
                    print(f"[auto-approve] gateway policy flagged '{tool_name}' -> approving")
                else:
                    prompt = f"Approve tool '{tool_name}' flagged by gateway policy? [y/N] "
                    answer = (await asyncio.to_thread(input, prompt)).strip().lower()
                    approved = answer in ("y", "yes")
                approvals.append(req.to_function_approval_response(approved=approved))
            result = await agent.run(Message(role="user", contents=approvals), session=session)
        print("\nAgent:", result.text)

        audit_log = config.get_audit_log()
        print(f"\nSecurity audit entries: {len(audit_log)}")
        for entry in audit_log:
            reason = entry.get("reason", "policy violation")
            function_name = entry.get("function", "unknown")
            print(f"  - function={function_name} reason={reason}")


async def run_devui_async(*, debug: bool = False, gateway_port: int = 9090) -> None:
    """Launch DevUI with both MCP proxies."""
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
                tools=secure_mcp.tools,
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


def _parse_args(argv: list[str]) -> tuple[str, bool, int, bool]:
    """Parse CLI arguments. Returns (mode, debug, gateway_port, auto_approve)."""
    parser = argparse.ArgumentParser(description="Run WorkIQ Email/Teams MCP + FIDES sample.")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--cli", action="store_true", help="Run in command line mode.")
    mode_group.add_argument("--devui", action="store_true", help="Run with DevUI web interface.")
    parser.add_argument("--debug", action="store_true", help="Enable verbose security logging.")
    parser.add_argument(
        "--gateway-port",
        type=int,
        default=9090,
        help="Port of the local Fides gateway (default: 9090).",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve gateway policy prompts in CLI mode (default: prompt interactively).",
    )
    args = parser.parse_args(argv)
    mode = "cli" if args.cli else "devui"
    return mode, args.debug, args.gateway_port, args.auto_approve


def main() -> None:
    """Entry point for the sample script."""
    mode, debug, gateway_port, auto_approve = _parse_args(sys.argv[1:])
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("agent_framework.security").setLevel(logging.DEBUG if debug else logging.WARNING)
    try:
        if mode == "cli":
            asyncio.run(run_cli_async(debug=debug, gateway_port=gateway_port, auto_approve=auto_approve))
        else:
            asyncio.run(run_devui_async(debug=debug, gateway_port=gateway_port))
    except RuntimeError as ex:
        print(f"\nError: {ex}", file=sys.stderr)
        raise SystemExit(1) from ex
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)


if __name__ == "__main__":
    main()
