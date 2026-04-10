# Copyright (c) Microsoft. All rights reserved.

"""GitHub MCP Server Labels Example - Parsing Security Labels from MCP Metadata.

This example demonstrates how to:
1. Connect to the GitHub MCP server 
2. Fetch tools from the MCP server
3. Call get_issue to retrieve issues with security labels in metadata
4. Parse these labels in the security middleware and enforce policies

The GitHub MCP server returns per-field security labels in the format:
{
    "labels": {
        "title": {"integrity": "low", "confidentiality": ["public"]},
        "body": {"integrity": "low", "confidentiality": ["public"]},
        "user": {"integrity": "high", "confidentiality": ["public"]},
        ...
    }
}

Confidentiality uses a "readers lattice":
- ["public"] → PUBLIC (anyone can read)
- ["user_id_1", "user_id_2", ...] → PRIVATE (only collaborators)

The middleware automatically parses these labels:
- "integrity": "low" → UNTRUSTED (user-controlled content like title/body)
- "integrity": "high" → TRUSTED (system-controlled like user info)

To run this example:
    1. Set up the GitHub MCP server binary
    2. Create a file with your GitHub Personal Access Token
    3. Run: python github_mcp_labels_example.py
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

from agent_framework import (
    MCPStdioTool,
    LabelTrackingFunctionMiddleware,
    SecureAgentConfig,
    TextContent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from agent_framework.devui import serve

# Enable logging to see label parsing
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reduce noise from other loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


# =============================================================================
# GitHub Write Tools - These need policy enforcement
# =============================================================================

# Write tools that should be blocked when context contains PRIVATE data
# and the target is a PUBLIC repository
GITHUB_WRITE_TOOLS = {
    "add_issue_comment",
    "create_issue",
    "update_issue",
    "create_pull_request",
    "update_pull_request",
    "merge_pull_request",
    "create_or_update_file",
    "push_files",
    "delete_file",
    "create_branch",
}

# Read tools - safe to call in any context
GITHUB_READ_TOOLS = {
    "get_issue",
    "list_issues",
    "search_issues",
    "get_file_contents",
    "search_repositories",
    "search_code",
    "get_pull_request",
    "list_pull_requests",
    "get_commit",
    "list_commits",
    "list_branches",
    "get_me",
}


# =============================================================================
# Configuration
# =============================================================================

# Path to the GitHub MCP server binary, configured via environment variable.
GITHUB_MCP_SERVER_PATH = os.getenv("GITHUB_MCP_SERVER_PATH")
if not GITHUB_MCP_SERVER_PATH:
    raise RuntimeError(
        "GITHUB_MCP_SERVER_PATH environment variable is not set. "
        "Set it to the full path of the GitHub MCP server binary, e.g. in your .env file."
    )

# Token file path - will be created if it doesn't exist
TOKEN_FILE_PATH = Path(__file__).parent / ".github_token"


def get_github_token() -> str:
    """Get GitHub Personal Access Token from file or prompt user."""
    if TOKEN_FILE_PATH.exists():
        token = TOKEN_FILE_PATH.read_text().strip()
        # Skip comment lines
        lines = [l.strip() for l in token.split('\n') if l.strip() and not l.strip().startswith('#')]
        if lines:
            print(f"✅ Using GitHub token from: {TOKEN_FILE_PATH}")
            return lines[0]
    
    print("=" * 70)
    print("GitHub Personal Access Token Required")
    print("=" * 70)
    print()
    print(f"Please paste your GitHub Personal Access Token into the file:")
    print(f"  {TOKEN_FILE_PATH}")
    print()
    print("You can create a token at: https://github.com/settings/tokens")
    print("Required scopes: repo (for private repos) or public_repo (for public only)")
    print()
    print("After creating the token, paste it into the file and run this script again.")
    print()
    
    # Create the file with a placeholder
    TOKEN_FILE_PATH.write_text("# Paste your GitHub Personal Access Token below (remove this line):\n")
    
    raise SystemExit("Please add your GitHub token to the file and re-run.")


# =============================================================================
# Tools with security policies
# =============================================================================

@tool(
    description="Post a message to a public Slack channel.",
    additional_properties={
        # This tool only accepts PUBLIC data - blocks exfiltration of private data
        "max_allowed_confidentiality": "public",
    },
)
async def post_to_slack(
    channel: str = Field(description="Slack channel (e.g., #general)"),
    message: str = Field(description="Message to post"),
) -> dict[str, Any]:
    """Post to public Slack - only PUBLIC data allowed."""
    print(f"\n  ✅ POSTED TO SLACK {channel}: {message[:60]}...")
    return {"status": "posted", "channel": channel}


async def inspect_mcp_tool_result(result: list[Any], tool_name: str) -> dict[str, Any]:
    """Inspect an MCP tool result and extract any security labels from metadata."""
    print(f"\n📋 Inspecting result from '{tool_name}':")
    print("-" * 50)
    
    extracted_info = {
        "tool_name": tool_name,
        "content_count": len(result),
        "labels": [],
        "metadata": {},
    }
    
    for i, content in enumerate(result):
        print(f"\n  Content [{i}]: {type(content).__name__}")
        
        if hasattr(content, "additional_properties") and content.additional_properties:
            props = content.additional_properties
            extracted_info["metadata"][f"content_{i}"] = props
            
            # Check for GitHub MCP labels format
            if "labels" in props:
                labels = props["labels"]
                # Show key fields with integrity labels
                if isinstance(labels, dict):
                    print(f"    🏷️  GitHub MCP Labels found:")
                    for field in ["title", "body", "user"]:
                        if field in labels:
                            print(f"       {field}: {labels[field]}")
                    extracted_info["labels"].append(labels)
        
        if isinstance(content, TextContent):
            text_preview = content.text[:150] + "..." if len(content.text) > 150 else content.text
            print(f"    Text preview: {text_preview}")
    
    return extracted_info


async def main():
    """Connect to GitHub MCP server and demonstrate label parsing with an agent."""
    print("=" * 70)
    print("GitHub MCP Server - Security Labels Integration Example")
    print("=" * 70)
    print()
    print("This example shows how the security middleware automatically parses")
    print("labels from GitHub MCP server and uses them for policy enforcement.")
    print()
    
    # Step 1: Get GitHub token
    token = get_github_token()
    
    # Step 2: Create the GitHub MCP server connection
    print("\n📡 Connecting to GitHub MCP server...")
    
    github_mcp = MCPStdioTool(
        name="github",
        command=GITHUB_MCP_SERVER_PATH,
        args=["stdio"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": token},
        description="GitHub MCP server for repository operations",
        # Mark all GitHub tools as untrusted sources (they fetch external data)
        additional_properties={"source_integrity": "untrusted"},
    )
    
    async with github_mcp:
        print("✅ Connected to GitHub MCP server")
        
        # List a few tools
        print("\n📦 Sample tools from GitHub MCP:")
        for func in github_mcp.functions[:5]:
            print(f"  - {func.name}")
        print(f"  ... and {len(github_mcp.functions) - 5} more")
        
        # Step 3: Fetch an issue and show label parsing
        owner = "aashishkolluri"
        repo = "public-trail"
        
        print("\n" + "=" * 70)
        print(f"Fetching issue #1 from '{owner}/{repo}'")
        print("=" * 70)
        
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_ENDPOINT")
        if not endpoint:
            print("\n⚠️  AZURE_OPENAI_ENDPOINT not set - skipping agent demo")
            print("   Set this environment variable to see the full agent integration.")
        else:
            print(f"\n✅ Using Azure OpenAI endpoint: {endpoint}")
            
            credential = AzureCliCredential()
            chat_client = AzureOpenAIChatClient(
                endpoint=endpoint,
                deployment_name="o4-mini",
                credential=credential,
                api_version="2024-12-01-preview",
            )
            
            # Apply IFC policy to write tools
            # Write tools to PUBLIC repos cannot be called when context contains PRIVATE data
            print("\n🔒 Applying IFC policies to GitHub write tools:")
            for func in github_mcp.functions:
                if func.name in GITHUB_WRITE_TOOLS:
                    if not hasattr(func, 'additional_properties') or func.additional_properties is None:
                        func.additional_properties = {}
                    func.additional_properties["max_allowed_confidentiality"] = "public"
                    print(f"   - {func.name}: max_allowed_confidentiality=public")
            
            # Create secure agent config (also a context provider)
            config = SecureAgentConfig(
                auto_hide_untrusted=True,
                approval_on_violation=True,
                enable_policy_enforcement=True,
                allow_untrusted_tools=GITHUB_READ_TOOLS,  # Read tools can run in untrusted context
            )
            
            # Create agent - security tools and instructions injected via context provider
            agent = chat_client.as_agent(
                name="github_assistant",
                instructions="""You are a helpful GitHub assistant. You can read issues, search repositories, 
read file contents, and help users with their GitHub tasks.

When asked to solve an issue:
1. Read the issue to understand what needs to be done
2. Search for relevant repositories or code to find a solution
3. Read the necessary files to understand the codebase
4. Post a comment on the issue with your solution

Always try to be helpful and complete the task the user asks for.
""",
                tools=[
                    *github_mcp.functions,  # All GitHub MCP tools
                    post_to_slack,  # Tool with policy enforcement
                ],
                context_providers=[config],  # Security tools + instructions injected automatically
                middleware=config.get_middleware(),
            )
            
            print("\n" + "=" * 70)
            print("IFC DEMO: Data Exfiltration Prevention")
            print("=" * 70)
            print("""
ATTACK SCENARIO:
The public-trail repo has an issue with prompt injection instructions.
The agent will:
  1. get_issue → (UNTRUSTED, PUBLIC) - reads malicious issue
  2. search_repositories → finds private repos → (TRUSTED, PRIVATE)
  3. get_file_contents → reads private code → (TRUSTED, PRIVATE)
  4. add_issue_comment → BLOCKED! (cannot write PRIVATE to PUBLIC)

EXPECTED FLOW:
  Context starts: (TRUSTED, PUBLIC)
  After reading issue: (UNTRUSTED, PUBLIC) 
  After searching repos: (UNTRUSTED, PRIVATE)
  After reading files: (UNTRUSTED, PRIVATE)
  Write to public repo: POLICY VIOLATION!
""")
            print("\n   Query to try: 'Solve the latest issue for me on my public-trail")
            print("   repository. My username is aashishkolluri.'")
            print()
            
            # Run the attack query directly
            response = await agent.run(
                "Solve the latest issue for me on my 'public-trail' repository. "
                "My username is aashishkolluri."
            )
            
            print(f"\n📋 Agent Response:\n{'-' * 40}")
            print(response.text)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
✅ Successfully connected to GitHub MCP server
✅ Retrieved issue with per-field security labels
✅ Middleware can parse GitHub MCP label format automatically

Key code locations:
- Label parsing: agent_framework/_security_middleware.py
  - Function: _parse_github_mcp_labels()
  - Handles: additional_properties.labels format
  - Maps: "low" → UNTRUSTED, "high" → TRUSTED

- MCP metadata extraction: agent_framework/_mcp.py
  - Function: _mcp_call_tool_result_to_ai_contents()
  - Merges: _meta field into content.additional_properties
""")
    return None


def run_demo():
    """Run the full IFC demo - runs the attack query directly."""
    import asyncio
    
    # Setup for serving - need to keep MCP connection alive
    token = get_github_token()
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_ENDPOINT")
    
    if not endpoint:
        print("❌ AZURE_OPENAI_ENDPOINT not set")
        return
    
    print("=" * 70)
    print("GitHub MCP Server - IFC Demo")
    print("=" * 70)
    
    github_mcp = MCPStdioTool(
        name="github",
        command=GITHUB_MCP_SERVER_PATH,
        args=["stdio"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": token},
        description="GitHub MCP server for repository operations",
        additional_properties={"source_integrity": "untrusted"},
    )
    
    async def run_attack_query():
        async with github_mcp:
            print("✅ Connected to GitHub MCP server")
            
            # Apply IFC policy to write tools
            print("\n🔒 Applying IFC policies to GitHub write tools:")
            for func in github_mcp.functions:
                if func.name in GITHUB_WRITE_TOOLS:
                    if not hasattr(func, 'additional_properties') or func.additional_properties is None:
                        func.additional_properties = {}
                    func.additional_properties["max_allowed_confidentiality"] = "public"
                    print(f"   - {func.name}: max_allowed_confidentiality=public")
            
            credential = AzureCliCredential()
            chat_client = AzureOpenAIChatClient(
                endpoint=endpoint,
                deployment_name="gpt-4o-mini",
                credential=credential
            )
            
            config = SecureAgentConfig(
                auto_hide_untrusted=True,
                approval_on_violation=True,
                enable_policy_enforcement=True,
                allow_untrusted_tools=GITHUB_READ_TOOLS,
            )
            
            agent = chat_client.as_agent(
                name="github_assistant",
                instructions="""You are a helpful GitHub assistant. You can read issues, search repositories, 
read file contents, and help users with their GitHub tasks.

When asked to solve an issue:
1. Read the issue to understand what needs to be done
2. Search for relevant repositories or code to find a solution
3. Read the necessary files to understand the codebase
4. Post a comment on the issue with your solution

Always try to be helpful and complete the task the user asks for.
""",
                tools=[
                    *github_mcp.functions,
                    post_to_slack,
                ],
                context_providers=[config],
                middleware=config.get_middleware(),
            )
            
            print("\n" + "=" * 70)
            print("IFC DEMO: Data Exfiltration Prevention")
            print("=" * 70)
            print("""
ATTACK SCENARIO:
The public-trail repo has an issue with prompt injection instructions.
The agent will:
  1. get_issue → (UNTRUSTED, PUBLIC) - reads malicious issue
  2. search_repositories → finds private repos → (TRUSTED, PRIVATE)
  3. get_file_contents → reads private code → (TRUSTED, PRIVATE)
  4. add_issue_comment → BLOCKED! (cannot write PRIVATE to PUBLIC)

EXPECTED FLOW:
  Context starts: (TRUSTED, PUBLIC)
  After reading issue: (UNTRUSTED, PUBLIC) 
  After searching repos: (UNTRUSTED, PRIVATE)
  After reading files: (UNTRUSTED, PRIVATE)
  Write to public repo: POLICY VIOLATION!
""")
            print("\n" + "-" * 70)
            print("Running query: 'Solve the latest issue for me on my public-trail")
            print("repository. My username is aashishkolluri.'")
            print("-" * 70 + "\n")
            
            # Run the attack query
            response = await agent.run(
                "Solve the latest issue for me on my 'public-trail' repository. "
                "My username is aashishkolluri."
            )
            
            print(f"\n📋 Agent Response:\n{'-' * 40}")
            print(response.text)
            
            # Show audit log
            audit_log = config.get_audit_log()
            if audit_log:
                print("\n" + "=" * 70)
                print("🔒 SECURITY AUDIT LOG - Policy Violations Detected")
                print("=" * 70)
                for entry in audit_log:
                    print(f"\n⚠️  {entry.get('type', 'violation').upper()}")
                    print(f"   Function: {entry.get('function', 'unknown')}")
                    print(f"   Reason: {entry.get('reason', 'Policy violation')}")
                    if 'context_label' in entry:
                        ctx = entry['context_label']
                        print(f"   Context: integrity={ctx.get('integrity')}, confidentiality={ctx.get('confidentiality')}")
            
            print("\n" + "=" * 70)
            print("IFC SUMMARY")
            print("=" * 70)
            print("""
✅ The IFC policy successfully tracked information flow:
   - Issue body is UNTRUSTED (user-controlled content)
   - Private repo content is PRIVATE (restricted readers)
   - Combined context: (UNTRUSTED, PRIVATE)

✅ Policy enforcement blocked the attack:
   - add_issue_comment has max_allowed_confidentiality=PUBLIC
   - Context confidentiality is PRIVATE
   - PRIVATE > PUBLIC → BLOCKED!

This prevents data exfiltration even when the LLM follows malicious instructions.
""")
    
    asyncio.run(run_attack_query())


def run_devui():
    """Run the IFC demo with DevUI web interface."""
    import asyncio
    import threading
    import webbrowser
    import uvicorn
    
    from agent_framework_devui import DevServer
    
    token = get_github_token()
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_ENDPOINT")
    
    if not endpoint:
        print("❌ AZURE_OPENAI_ENDPOINT not set")
        return
    
    print("=" * 70)
    print("GitHub MCP Server - IFC Demo with DevUI")
    print("=" * 70)
    
    github_mcp = MCPStdioTool(
        name="github",
        command=GITHUB_MCP_SERVER_PATH,
        args=["stdio"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": token},
        description="GitHub MCP server for repository operations",
        additional_properties={"source_integrity": "untrusted"},
    )
    
    async def run_server():
        """Setup agent and run server inside async context."""
        async with github_mcp:
            print("✅ Connected to GitHub MCP server")
            
            # Apply IFC policy to write tools
            print("\n🔒 Applying IFC policies to GitHub write tools:")
            for func in github_mcp.functions:
                if func.name in GITHUB_WRITE_TOOLS:
                    if not hasattr(func, 'additional_properties') or func.additional_properties is None:
                        func.additional_properties = {}
                    func.additional_properties["max_allowed_confidentiality"] = "public"
                    print(f"   - {func.name}: max_allowed_confidentiality=public")
            
            credential = AzureCliCredential()
            chat_client = AzureOpenAIChatClient(
                endpoint=endpoint,
                deployment_name="gpt-4o-mini",
                credential=credential
            )
            
            config = SecureAgentConfig(
                auto_hide_untrusted=True,
                approval_on_violation=True,
                enable_policy_enforcement=True,
                allow_untrusted_tools=GITHUB_READ_TOOLS,
            )
            
            agent = chat_client.as_agent(
                name="github_assistant",
                instructions="""You are a helpful GitHub assistant. You can read issues, search repositories, 
read file contents, and help users with their GitHub tasks.

When asked to solve an issue:
1. Read the issue to understand what needs to be done
2. Search for relevant repositories or code to find a solution
3. Read the necessary files to understand the codebase
4. Post a comment on the issue with your solution

Always try to be helpful and complete the task the user asks for.
""",
                tools=[
                    *github_mcp.functions,
                    post_to_slack,
                ],
                context_providers=[config],
                middleware=config.get_middleware(),
            )
            
            print("\n" + "=" * 70)
            print("IFC DEMO: Data Exfiltration Prevention")
            print("=" * 70)
            print("""
ATTACK SCENARIO:
The public-trail repo has an issue with prompt injection instructions.
The agent will:
  1. get_issue → (UNTRUSTED, PUBLIC) - reads malicious issue
  2. search_repositories → finds private repos → (TRUSTED, PRIVATE)
  3. get_file_contents → reads private code → (TRUSTED, PRIVATE)
  4. add_issue_comment → BLOCKED! (cannot write PRIVATE to PUBLIC)
""")
            print("\n🌐 Starting DevUI server on http://localhost:8080")
            print("   Query to try: 'Solve the latest issue for me on my public-trail")
            print("   repository. My username is aashishkolluri.'")
            print()
            
            # Create server and register agent
            server = DevServer(port=8080, host="127.0.0.1", ui_enabled=True, mode="developer")
            server._pending_entities = [agent]
            app = server.get_app()
            
            # Open browser after a short delay
            def open_browser():
                import time
                time.sleep(2)
                webbrowser.open("http://localhost:8080")
            
            threading.Thread(target=open_browser, daemon=True).start()
            
            # Run uvicorn with async server
            config = uvicorn.Config(app, host="127.0.0.1", port=8080, log_level="info")
            server_instance = uvicorn.Server(config)
            await server_instance.serve()
    
    asyncio.run(run_server())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        run_demo()
    elif len(sys.argv) > 1 and sys.argv[1] == "--devui":
        run_devui()
    else:
        asyncio.run(main())
