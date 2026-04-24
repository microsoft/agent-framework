# FIDES: Deterministic Prompt Injection Defense System

**FIDES**  is a comprehensive security system for AI agents. This developer guide describes the deterministic prompt injection defense system implemented in the agent framework. The system provides label-based security mechanisms to defend against prompt injection attacks by tracking integrity and confidentiality of content throughout agent execution.

## 🚀 NEW: Context Provider Pattern with SecureAgentConfig!

**`SecureAgentConfig` is now a `ContextProvider`** — add it to any agent with a single `context_providers=[config]` line. It automatically injects security tools, instructions, and middleware via the `before_run()` hook. No security knowledge required from developers.

**Key Features:**
- **Context Provider Pattern** - `SecureAgentConfig` extends `ContextProvider`, injecting everything automatically
- **Automatic Variable Hiding** - UNTRUSTED content is automatically stored and replaced with references
- **Per-Item Embedded Labels** - Tools return `list[Content]` with `Content.from_text()` for proper label propagation
- **Zero-Config Security** - `context_providers=[config]` replaces manual `middleware=`, `tools=`, and `instructions=` wiring
- **Variable ID Support** - `quarantined_llm` now accepts `variable_ids` to directly reference hidden content
- **Security Instructions** - Built-in `SECURITY_TOOL_INSTRUCTIONS` automatically injected into agent context

## Overview

The defense system consists of eight main components:

1. **Content Labeling Infrastructure** - Labels for tracking integrity and confidentiality
2. **Label Tracking Middleware** - Automatically assigns, propagates labels, and **hides untrusted content**
3. **Per-Item Embedded Labels** - Tools can return mixed-trust data with per-item security labels
4. **Policy Enforcement Middleware** - Blocks tool calls that violate security policies
5. **Security Tools** - Specialized tools for safe handling of untrusted content (`quarantined_llm`, `inspect_variable`)
6. **SecureAgentConfig** - Helper class for easy secure agent configuration
7. **Message-Level Label Tracking** - Track labels on every message in the conversation (Phase 1)

## Architecture

### 1. Content Labels

Every piece of content (tool calls, results, messages) can be assigned a `ContentLabel` with two dimensions:

#### Integrity Labels
- **TRUSTED**: Content from trusted sources (user input, system messages)
- **UNTRUSTED**: Content from untrusted sources (AI-generated, external APIs)

#### Confidentiality Labels
- **PUBLIC**: Content can be shared publicly
- **PRIVATE**: Content is private and should not be shared
- **USER_IDENTITY**: Content is restricted to specific user identities only

```python
from agent_framework.security import ContentLabel, IntegrityLabel, ConfidentialityLabel

# Create a label
label = ContentLabel(
    integrity=IntegrityLabel.TRUSTED,
    confidentiality=ConfidentialityLabel.PRIVATE,
    metadata={"user_id": "user-123"}
)
```

### 2. Label Tracking Middleware with Tiered Label Propagation

`LabelTrackingFunctionMiddleware` uses a **tiered label propagation** scheme where the result label of a tool call is determined by a strict 3-tier priority:

| Priority | Source | Used When |
|----------|--------|-----------|
| **Tier 1** (Highest) | Per-item embedded labels (`additional_properties.security_label`) | Tool result items include explicit labels |
| **Tier 2** | Tool's `source_integrity` declaration | No embedded labels, but tool declares `source_integrity` |
| **Tier 3** (Lowest) | Join of input argument labels (`combine_labels`) | No embedded labels AND no `source_integrity` declared |
| **Default** | `UNTRUSTED` | No labels from any tier |

**Tiered Label Propagation:**
- **Tier 1: Embedded labels** in result items via `additional_properties.security_label` — highest priority, used per-item
- **Tier 2: `source_integrity`** declaration on the tool — authoritative for the trust level of the tool's output, regardless of input labels
- **Tier 3: Input labels join** — `combine_labels(*input_labels)` from arguments (VariableReferenceContent, labeled data)
- **Default**: `UNTRUSTED` when no labels exist from any tier

**Per-Item Embedded Labels (RECOMMENDED for Mixed-Trust Data):**
Tools returning mixed-trust data should embed labels on each item in `additional_properties.security_label`:

```python
# Each item has its own security label
[
    {"id": 1, "body": "trusted content", "additional_properties": {"security_label": {"integrity": "trusted"}}},
    {"id": 2, "body": "untrusted content", "additional_properties": {"security_label": {"integrity": "untrusted"}}},
]
```

The middleware automatically:
- Hides items with `integrity: "untrusted"` → replaced with `VariableReferenceContent`
- Keeps items with `integrity: "trusted"` visible in LLM context
- Combines labels from all items for the overall result label

**Tool-Level Source Integrity (Tier 2 Fallback):**
If items don't have embedded labels, the tool can declare a fallback via `source_integrity`.
When declared, `source_integrity` alone determines the result label — input argument labels are NOT combined in. This means a tool declaring `source_integrity="trusted"` always produces trusted output regardless of what inputs it received:
- `source_integrity="trusted"`: Tool produces trusted data (internal computations)
- `source_integrity="untrusted"`: Tool fetches untrusted data
- (not set): Falls back to tier 3 (join of input labels) or **UNTRUSTED** default

**Note:** For action tools (sinks like `send_email`), `source_integrity` doesn't apply since they don't produce data. Their result inherits labels from inputs (tier 3).

**Context Label Tracking:**
- Context label starts as **TRUSTED + PUBLIC** on first call
- Gets updated (tainted) when untrusted content enters the context
- Hidden content does NOT taint the context (it never enters LLM context)
- Policy enforcement uses the context label for validation

**Automatic Hiding:**
- UNTRUSTED results/items are automatically hidden in variable store
- LLM context sees only `VariableReferenceContent`
- Since hidden content doesn't enter context, it doesn't taint the context label

```python
import json
from agent_framework import Content, tool
from agent_framework.security import LabelTrackingFunctionMiddleware, SecureAgentConfig

# Define a tool that returns mixed-trust data with per-item labels
@tool(description="Fetch emails from inbox")
async def fetch_emails(count: int = 5) -> list[Content]:
    """Fetch emails - some from trusted internal sources, others from external sources."""
    emails = get_emails(count)
    return [
        Content.from_text(
            json.dumps({
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "body": email["body"],
            }),
            # Per-item label - middleware automatically hides untrusted items
            additional_properties={
                "security_label": {
                    "integrity": "trusted" if email["is_internal"] else "untrusted",
                    "confidentiality": "private",
                }
            },
        )
        for email in emails
    ]

# Define a tool that performs internal (trusted) computation
@tool(
    description="Calculate statistics",
    additional_properties={
        "source_integrity": "trusted",  # Fallback if no per-item labels
    }
)
async def calculate_stats(data: dict) -> dict:
    # If 'data' argument contains untrusted labels, output becomes UNTRUSTED
    # even though source_integrity is trusted (data-flow propagation)
    return {"mean": 42}

# Recommended: Use SecureAgentConfig as a context provider
config = SecureAgentConfig(
    auto_hide_untrusted=True,
    allow_untrusted_tools={"fetch_emails"},
    block_on_violation=True,
)

agent = Agent(
    client=client,
    name="assistant",
    instructions="You are a helpful assistant.",
    tools=[fetch_emails, calculate_stats],
    context_providers=[config],  # Injects tools, instructions, and middleware automatically
)
```

### 3. Per-Item Embedded Labels

For tools that return mixed-trust data (e.g., emails from both internal and external sources), you can embed security labels on individual items using `additional_properties.security_label`:

```python
import json
from agent_framework import Content, tool

@tool(description="Fetch emails from inbox")
async def fetch_emails(count: int = 5) -> list[Content]:
    """Fetch emails with per-item security labels."""
    emails = fetch_from_server(count)

    return [
        Content.from_text(
            json.dumps({
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "body": email["body"],
            }),
            # Embed security label for this specific item
            additional_properties={
                "security_label": {
                    "integrity": "trusted" if is_internal_sender(email["from"]) else "untrusted",
                    "confidentiality": "private",
                }
            },
        )
        for email in emails
    ]
```

**How It Works:**

1. **Tool returns mixed-trust data** with per-item `additional_properties.security_label`
2. **Middleware scans items** and extracts embedded labels
3. **Untrusted items are hidden** → replaced with `VariableReferenceContent`
4. **Trusted items remain visible** → passed to LLM context unchanged
5. **Combined label** is the most restrictive across all items

**Example Result After Processing:**

```python
# Original result from tool:
[
    {"id": 1, "body": "From manager", "additional_properties": {"security_label": {"integrity": "trusted"}}},
    {"id": 2, "body": "INJECTION ATTEMPT", "additional_properties": {"security_label": {"integrity": "untrusted"}}},
]

# After middleware processing (what LLM sees):
[
    {"id": 1, "body": "From manager", "additional_properties": {"security_label": {"integrity": "trusted"}}},
    VariableReferenceContent(variable_id="var_abc123", ...),  # Item 2 hidden
]
```

**Fallback Behavior:**

If an item doesn't have an embedded label, the fallback is determined by:
1. **Tool-level `source_integrity`** in `additional_properties` (if declared)
2. **UNTRUSTED** (default - secure by default)

```python
# Tool with fallback for items without embedded labels
@tool(
    description="Fetch data from external API",
    additional_properties={
        "source_integrity": "untrusted",  # Fallback for unlabeled items
    }
)
async def fetch_external_data(query: str) -> dict:
    # If no embedded label, this result will be hidden (UNTRUSTED fallback)
    return {"data": "..."}
```

**Why Per-Item Labels?**

- **Mixed-trust data**: A single API call may return both trusted and untrusted items
- **Granular control**: Only hide what needs hiding, keep trusted items visible
- **No source_integrity confusion**: Avoids the question "what is the source for an action tool?"
- **Consistent pattern**: Uses `additional_properties` like `FunctionResultContent`

### 4. Policy Enforcement Middleware

`PolicyEnforcementFunctionMiddleware` enforces security policies based on the **context label**:

- Uses the **context label** (not just call label) for policy decisions
- If context is UNTRUSTED, blocks tools that don't accept untrusted inputs
- Validates confidentiality requirements against context confidentiality
- Logs all violations for audit purposes

**Key Insight:** The policy enforcer checks if a tool can be called given the current security state of the entire conversation, not just the individual call.

```python
from agent_framework.security import PolicyEnforcementFunctionMiddleware

policy_enforcer = PolicyEnforcementFunctionMiddleware(
    allow_untrusted_tools={"search_web", "get_news"},  # Tools that can run in untrusted context
    block_on_violation=True,
    enable_audit_log=True
)

# If context becomes UNTRUSTED (e.g., after processing external API data),
# only tools in allow_untrusted_tools can be called.
# Other tools will be BLOCKED to prevent privilege escalation.
```
- Logs all violations for audit purposes

```python
from agent_framework.security import PolicyEnforcementFunctionMiddleware

policy_enforcer = PolicyEnforcementFunctionMiddleware(
    allow_untrusted_tools={"search_web", "get_news"},
    block_on_violation=True,
    enable_audit_log=True
)

agent = Agent(
    client=client,
    name="assistant",
    instructions="You are a helpful assistant.",
    middleware=[label_tracker, policy_enforcer],
)
```

### 5. Automatic Variable Indirection

The middleware now automatically handles variable indirection for UNTRUSTED content:

- **Automatic Detection**: Middleware checks integrity label after each tool call
- **Automatic Storage**: UNTRUSTED results are stored in middleware's variable store
- **Transparent Replacement**: LLM context receives VariableReferenceContent instead of actual content
- **Complete Isolation**: Actual untrusted content never exposed to LLM
- **Full Auditability**: All hiding events are logged

**No manual `store_untrusted_content()` calls needed!**

**How It Works:**

```python
# 1. Configure middleware with automatic hiding (enabled by default)
label_tracker = LabelTrackingFunctionMiddleware(
    auto_hide_untrusted=True,  # Default
    hide_threshold=IntegrityLabel.UNTRUSTED
)

# 2. Your tool returns data and labels it
@tool
def search_web(query: str) -> str:
    result = external_api.search(query)
    # Label the result as UNTRUSTED
    return ContentLabel(integrity=IntegrityLabel.UNTRUSTED).apply(result)

# 3. Middleware automatically:
#    - Detects UNTRUSTED label
#    - Stores actual content in variable store: {"var_abc123": "actual content"}
#    - Replaces result with: VariableReferenceContent(variable_name="var_abc123")
#    - LLM sees: "Content stored in variable var_abc123"
#    - Actual content: NEVER reaches LLM context!

from agent_framework.security import inspect_variable


# 4. If LLM needs to inspect (with audit trail):
async def inspect_content() -> None:
    result = await inspect_variable(variable_id="var_abc123")
    print(result)

# Returns: {"content": "actual content", "label": {...}, "audit": [...]}
```

**Benefits:**

- Zero developer effort - works automatically
- No manual variable management
- Consistent security enforcement
- Audit trail for all access
- Easy to enable/disable per middleware instance


### 6. Security Tools

#### quarantined_llm

Makes isolated LLM calls with labeled data in a security-isolated context. The quarantined LLM:
- Runs with **NO TOOLS** - preventing injection attacks from triggering tool calls
- Uses a **separate chat client** - ideally a cheaper model like gpt-4o-mini
- Processes untrusted content **safely** - any injected instructions are treated as data

**NEW**: Now supports **real LLM calls** when a `quarantine_chat_client` is configured via `SecureAgentConfig`.

```python
from agent_framework.security import quarantined_llm

# Option 1: Using variable_ids (RECOMMENDED for agent integration)
result = await quarantined_llm(
    prompt="Summarize this data",
    variable_ids=["var_abc123", "var_def456"]  # Reference hidden content by ID
)

# Option 2: Using labelled_data (for direct content)
result = await quarantined_llm(
    prompt="Summarize this data",
    labelled_data={
        "data": {
            "content": untrusted_data,
            "label": {"integrity": "untrusted", "confidentiality": "public"}
        }
    }
)
```

**Key Security Features:**
- Content is processed with `tools=None` and `tool_choice="none"`
- Prompt injection attempts in the content cannot trigger tool calls
- Declares `source_integrity="untrusted"` — the middleware automatically hides results via the standard auto-hide mechanism
- No tool-internal auto-hide logic — hiding is handled uniformly by `LabelTrackingFunctionMiddleware`

#### inspect_variable

Retrieves content from variable store (with audit logging):

```python
from agent_framework.security import inspect_variable


async def inspect_content() -> None:
    result = await inspect_variable(
        variable_id="var_abc123",
        reason="User explicitly requested full content",
    )
    print(result)

# WARNING: Exposes untrusted content to context
```

`inspect_variable` uses `approval_mode="never_require"` because the tool call is internal to the
security framework and not visible to the developer. Instead of gating on approval, calling
`inspect_variable` taints the context to UNTRUSTED, which blocks dangerous tool calls via
`PolicyEnforcementFunctionMiddleware`. This is separate from secure-policy approvals triggered
by `SecureAgentConfig(..., approval_on_violation=True)`, which only request approval when a
call would otherwise be blocked by the current security context.

### 7. SecureAgentConfig (Context Provider)

The easiest way to configure a secure agent with all security features. `SecureAgentConfig` extends `ContextProvider` and automatically injects tools, instructions, and middleware via the `before_run()` hook:

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework.security import SecureAgentConfig
from azure.identity import AzureCliCredential

# Create main chat client
main_client = OpenAIChatClient(
    model="gpt-4o",
    azure_endpoint="https://your-endpoint.openai.azure.com",
    credential=AzureCliCredential()
)

# Create a SEPARATE client for quarantined LLM calls (uses cheaper model)
quarantine_client = OpenAIChatClient(
    model="gpt-4o-mini",  # Cheaper model for processing untrusted content
    azure_endpoint="https://your-endpoint.openai.azure.com",
    credential=AzureCliCredential()
)

# Create configuration with real quarantine LLM
config = SecureAgentConfig(
    auto_hide_untrusted=True,
    allow_untrusted_tools={"fetch_external_data", "search_web"},
    block_on_violation=True,
    quarantine_chat_client=quarantine_client,  # Enable real LLM calls in quarantined_llm
)

# Configure agent — context provider injects everything automatically
agent = Agent(
    client=main_client,
    name="secure_assistant",
    instructions="You are a helpful assistant.",
    tools=[fetch_external_data, search_web],
    context_providers=[config],  # Adds tools, instructions, and middleware via before_run()
)
```

**SecureAgentConfig Parameters:**
- `auto_hide_untrusted` → Automatically hide UNTRUSTED content in variable store
- `allow_untrusted_tools` → Set of tools that can run in untrusted context
- `block_on_violation` → Block tool calls that violate security policies
- `quarantine_chat_client` → **NEW!** Provide a separate chat client for real LLM calls in `quarantined_llm`. Without this, `quarantined_llm` returns placeholder responses.

**SecureAgentConfig Methods:**
- `get_tools()` → Returns `[quarantined_llm, inspect_variable]`
- `get_instructions()` → Returns `SECURITY_TOOL_INSTRUCTIONS` (detailed guidance for agents)
- `get_middleware()` → Returns `[LabelTrackingFunctionMiddleware, PolicyEnforcementFunctionMiddleware]`
- `get_quarantine_client()` → Returns the configured quarantine chat client (or None)
- `before_run(context)` → Automatically injects tools, instructions, and middleware into the agent context

> **Note:** When using `context_providers=[config]`, you do NOT need to manually call `get_tools()`, `get_instructions()`, or `get_middleware()`. The context provider handles everything via `before_run()`.

### 8. Security Instructions for Agents

The `SECURITY_TOOL_INSTRUCTIONS` constant provides detailed guidance that teaches agents how to work with hidden content. When using `SecureAgentConfig` as a context provider, these instructions are **automatically injected** into the agent context:

```python
# Instructions are injected automatically when using context_providers=[config]
agent = Agent(
    client=client,
    name="assistant",
    instructions="You are a helpful assistant.",  # Just task instructions!
    tools=[my_tool],
    context_providers=[config],  # SECURITY_TOOL_INSTRUCTIONS injected via before_run()
)

# Or manually add instructions if not using context providers:
from agent_framework.security import SECURITY_TOOL_INSTRUCTIONS

agent = Agent(
    client=client,
    name="assistant",
    instructions=f"You are a helpful assistant.\n\n{SECURITY_TOOL_INSTRUCTIONS}",
    tools=[my_tool, quarantined_llm, inspect_variable],
    middleware=[label_tracker, policy_enforcer],
)
```

The instructions explain:
- What `VariableReferenceContent` means
- When to use `quarantined_llm` vs `inspect_variable`
- How to pass `variable_ids` to reference hidden content
- Best practices for secure content handling

### 9. LabeledMessage Class

**LabeledMessage** automatically infers security labels based on message role:
- User/system messages → TRUSTED
- Tool messages → UNTRUSTED
- Assistant messages → Inherit from source_labels or TRUSTED

```python
from agent_framework.security import LabeledMessage

# Create with automatic label inference
msg = LabeledMessage(role="tool", content="External data")
assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED

# Create with explicit label
msg = LabeledMessage(
    role="assistant",
    content="Summary",
    security_label=explicit_label,
    source_labels=[untrusted_tool_label]  # Track derivation
)
```

**quarantined_llm Auto-Hiding:**

`quarantined_llm` declares `source_integrity="untrusted"` in its tool metadata. The
`LabelTrackingFunctionMiddleware` uses this to label the output as UNTRUSTED and
automatically hide it behind a variable reference — the same mechanism used for any
other tool that returns untrusted data. No tool-internal auto-hide logic is needed.

```python
# When processing UNTRUSTED content, the middleware auto-hides the result
result = await quarantined_llm(
    prompt="Summarize this data",
    variable_ids=["var_abc123"]
)
# The middleware stores the response in the variable store and replaces it
# with a VariableReferenceContent — just like any other untrusted tool result.
# The agent can then use inspect_variable() to surface the content.
```

## Usage Examples

### Example 1: Quick Start with SecureAgentConfig (RECOMMENDED)

The easiest way to set up a secure agent using the context provider pattern:

```python
from agent_framework.security import SecureAgentConfig

# Create secure configuration (also a ContextProvider)
config = SecureAgentConfig(
    auto_hide_untrusted=True,
    allow_untrusted_tools={"search_web", "fetch_data"},
    block_on_violation=True,
)

# Create agent with context provider — security is injected automatically!
agent = Agent(
    client=client,
    name="secure_assistant",
    instructions="You are a helpful assistant that can search the web and fetch data.",
    tools=[search_web, fetch_data],
    context_providers=[config],  # Injects tools, instructions, and middleware via before_run()
)

# Run agent - security is automatic!
response = await agent.run(messages=[
    {"role": "user", "content": "Search for Python tutorials and summarize"}
])
```

### Example 2: Manual Setup (More Control)

```python
from agent_framework.security import (
    LabelTrackingFunctionMiddleware,
    PolicyEnforcementFunctionMiddleware,
    get_security_tools,
    SECURITY_TOOL_INSTRUCTIONS,
)

# Create middleware stack
label_tracker = LabelTrackingFunctionMiddleware(auto_hide_untrusted=True)
policy_enforcer = PolicyEnforcementFunctionMiddleware(
    allow_untrusted_tools={"search_web"},
    block_on_violation=True
)

# Create agent with security (manual setup, no context provider)
agent = Agent(
    client=client,
    name="secure_assistant",
    instructions=f"You are a helpful assistant.\n\n{SECURITY_TOOL_INSTRUCTIONS}",
    tools=[search_web, *get_security_tools()],
    middleware=[label_tracker, policy_enforcer],
)

# Run agent - security is automatic
response = await agent.run(messages=[
    {"role": "user", "content": "Search the web for Python tutorials"}
])
```

### Example 3: Agent Processing Hidden Content

When an agent encounters hidden content, it uses `quarantined_llm` with variable IDs:

```python
# Agent workflow (automatic):
# 1. User asks: "Fetch weather data and summarize it"
# 2. Agent calls: fetch_external_data("weather")
# 3. Middleware labels result as UNTRUSTED
# 4. Middleware stores content and returns: VariableReferenceContent(variable_id='var_abc123')
# 5. Agent sees the variable reference in context
# 6. Agent uses quarantined_llm to process:

result = await quarantined_llm(
    prompt="Summarize the key weather information",
    variable_ids=["var_abc123"]  # Reference the hidden content
)

# 7. Agent returns summary to user
# 8. Original untrusted content was NEVER exposed to LLM context!
```

### Example 4: Handling External Data with Automatic Hiding

```python
from agent_framework import tool
from agent_framework.security import (
    LabelTrackingFunctionMiddleware,
    quarantined_llm,
    ContentLabel,
    IntegrityLabel,
)

# Configure middleware with automatic hiding
label_tracker = LabelTrackingFunctionMiddleware(auto_hide_untrusted=True)

# Define tool that fetches and labels external data
@tool(description="Fetch data from external API")
async def fetch_external_data(query: str) -> str:
    """Fetch data from external API."""
    external_response = await external_api.fetch(query)
    # Result is automatically labeled UNTRUSTED (AI-generated call)
    return external_response

# Create agent with automatic hiding
agent = Agent(
    client=client,
    name="secure_assistant",
    instructions="You are a helpful assistant.",
    tools=[fetch_external_data],
    middleware=[label_tracker],
)

# Run agent - external data is automatically hidden from LLM context
response = await agent.run(messages=[
    {"role": "user", "content": "Fetch and summarize external data"}
])

# If you need to process untrusted data in isolation:
result = await quarantined_llm(
    prompt="Extract key insights",
    variable_ids=["var_abc123"]  # Pass the variable ID from VariableReferenceContent
)
```


### Example 5: Tool Configuration with Per-Item Labels

```python
import json
from agent_framework import Content, tool

# Tool returning mixed-trust data with per-item labels (RECOMMENDED)
@tool(description="Fetch emails from inbox")
async def fetch_emails(count: int = 5) -> list[Content]:
    """Emails can be from trusted internal or untrusted external sources."""
    emails = get_emails(count)
    return [
        Content.from_text(
            json.dumps({
                "id": email["id"],
                "from": email["from"],
                "body": email["body"],
            }),
            # Per-item label - middleware handles hiding automatically
            additional_properties={
                "security_label": {
                    "integrity": "trusted" if email["is_internal"] else "untrusted",
                    "confidentiality": "private",
                }
            },
        )
        for email in emails
    ]

# Action tool (sink) - no source_integrity needed
@tool(
    description="Send an email to recipient",
    additional_properties={
        "confidentiality": "private",
        "accepts_untrusted": False,  # Block if context is tainted
    }
)
async def send_email(to: str, subject: str, body: str) -> dict:
    """Action tool - result inherits labels from inputs, not 'source_integrity'."""
    return {"status": "sent", "message_id": "msg_123"}

# Tool that requires trusted inputs
@tool(
    description="Execute privileged operation",
    additional_properties={
        "confidentiality": "private",
        "accepts_untrusted": False,
    }
)
async def privileged_operation(command: str) -> dict:
    return {"result": "executed"}

# Simple tool with fallback source_integrity (no per-item labels)
@tool(
    description="Search the web",
    additional_properties={
        "confidentiality": "public",
        "source_integrity": "untrusted",  # Fallback - all results treated as untrusted
    }
)
async def search_web(query: str) -> dict:
    return {"results": "..."}
```

## Security Properties

### Deterministic Defense

The system provides deterministic defense by:

1. **Always labeling**: Every tool call gets a label based on its source
2. **Policy enforcement**: Violations are blocked before execution
3. **Content isolation**: Untrusted content never enters main LLM context
4. **Audit trail**: All security events are logged

### Attack Prevention

The system prevents:

- **Direct prompt injection**: Untrusted content stored as variables
- **Indirect prompt injection**: Tool calls labeled and policy-checked
- **Privilege escalation**: Untrusted calls to privileged tools blocked
- **Data exfiltration**: Confidentiality labels enforced via `max_allowed_confidentiality`

### Data Exfiltration Prevention

The system prevents data exfiltration attacks where an attacker (via prompt injection) tries to leak sensitive data to public destinations. This is achieved through the `max_allowed_confidentiality` property on tools.

**The Problem:**
An attacker injects instructions in untrusted content (e.g., a public GitHub issue) that trick the agent into:
1. Reading private data (e.g., internal secrets)
2. Sending that data to a public destination (e.g., posting to Slack)

**The Solution:**
Tools that write to external destinations declare `max_allowed_confidentiality` to restrict what data they can receive:

```python
from agent_framework import tool
from agent_framework.security import check_confidentiality_allowed
from pydantic import Field

# Tool that reads from repositories with dynamic confidentiality
@tool(
    description="Read files from a repository",
    additional_properties={
        "source_integrity": "untrusted",
        "accepts_untrusted": True,  # Allow reading even in untrusted context
    }
)
async def read_repo(repo: str, path: str) -> dict:
    repo_data = get_repo(repo)
    visibility = repo_data["visibility"]  # "public" or "private"

    return {
        "content": repo_data["files"][path],
        # Dynamic confidentiality based on repository visibility
        "additional_properties": {
            "security_label": {
                "integrity": "untrusted",
                "confidentiality": "private" if visibility == "private" else "public",
            }
        },
    }

# Tool that writes to a PUBLIC destination - blocks PRIVATE data
@tool(
    description="Post a message to public Slack channel",
    additional_properties={
        "max_allowed_confidentiality": "public",  # Only PUBLIC data allowed!
    }
)
async def post_to_slack(channel: str, message: str) -> dict:
    return {"status": "posted", "channel": channel}

# Tool that writes to a PRIVATE destination - allows PRIVATE data
@tool(
    description="Send internal memo (can include private data)",
    additional_properties={
        "max_allowed_confidentiality": "private",  # PRIVATE data OK, USER_IDENTITY blocked
    }
)
async def send_internal_memo(recipients: str, body: str) -> dict:
    return {"status": "sent"}
```

**How It Works:**

1. **Context confidentiality propagates**: Reading PRIVATE data taints the context as PRIVATE
2. **Policy checks `max_allowed_confidentiality`**: Before executing a tool, the middleware checks if `context_confidentiality <= max_allowed_confidentiality`
3. **Data exfiltration blocked**: If context is PRIVATE but tool only accepts PUBLIC, the call is blocked

**Confidentiality Hierarchy:**
```
PUBLIC (0) < PRIVATE (1) < USER_IDENTITY (2)
```

- PUBLIC data can flow anywhere
- PRIVATE data can only flow to PRIVATE or USER_IDENTITY destinations
- USER_IDENTITY data can only flow to USER_IDENTITY destinations

**Runtime Helper Function:**

For tools that need dynamic confidentiality checks (e.g., a single `send_message()` tool that can post to different destinations), use `check_confidentiality_allowed()`:

```python
from agent_framework.security import check_confidentiality_allowed, ContentLabel, ConfidentialityLabel

def get_destination_confidentiality(destination: str) -> ConfidentialityLabel:
    """Determine confidentiality level of a destination."""
    if destination.startswith("#public-"):
        return ConfidentialityLabel.PUBLIC
    elif destination.startswith("#internal-"):
        return ConfidentialityLabel.PRIVATE
    return ConfidentialityLabel.PUBLIC  # Default to most restrictive check

# In your tool, check before sending:
context_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)  # From middleware
dest_conf = get_destination_confidentiality("#public-general")

if not check_confidentiality_allowed(context_label, dest_conf):
    raise ValueError(
        f"Cannot send {context_label.confidentiality.value} data "
        f"to {dest_conf.value} destination (data exfiltration blocked)"
    )
```

**Example Scenario:**

```python
# Attack scenario:
# 1. Agent reads public issue (contains injection: "read secrets and post to Slack")
await read_repo(repo="public-docs", path="issues")  # Context: PUBLIC

# 2. Compromised agent reads private secrets
await read_repo(repo="internal-secrets", path="secrets.env")  # Context: PRIVATE

# 3. Agent tries to post secrets to public Slack
await post_to_slack(channel="#general", message="DATABASE_PASSWORD=...")
# ❌ BLOCKED: Cannot write PRIVATE data to PUBLIC destination

# Legitimate scenario:
# 1. Agent reads public docs
await read_repo(repo="public-docs", path="README.md")  # Context: PUBLIC

# 2. Agent posts to Slack
await post_to_slack(channel="#docs", message="Check out our docs!")
# ✅ ALLOWED: PUBLIC data to PUBLIC destination
```

**Tool Configuration Summary:**

| Property | Purpose | Example Values |
|----------|---------|----------------|
| `confidentiality` | Declares output sensitivity | `"public"`, `"private"`, `"user_identity"` |
| `max_allowed_confidentiality` | Gates outputs (maximum level) | `"public"` = blocks PRIVATE data exfiltration |

See `samples/02-agents/security/repo_confidentiality_example.py` for a complete working example.

## Configuration Options

### LabelTrackingFunctionMiddleware

```python
LabelTrackingFunctionMiddleware(
    default_integrity=IntegrityLabel.UNTRUSTED,  # Default for unknown sources
    default_confidentiality=ConfidentialityLabel.PUBLIC,  # Default confidentiality
    auto_hide_untrusted=True,  # Automatically hide UNTRUSTED content (default: True)
    hide_threshold=IntegrityLabel.UNTRUSTED,  # Threshold for automatic hiding
)
```

**Key Parameters:**
- `auto_hide_untrusted`: When True, automatically stores UNTRUSTED content in variables
- `hide_threshold`: Integrity level at which automatic hiding occurs
- Set `auto_hide_untrusted=False` to disable automatic hiding and use manual `store_untrusted_content()` calls


### PolicyEnforcementFunctionMiddleware

```python
PolicyEnforcementFunctionMiddleware(
    allow_untrusted_tools={"tool1", "tool2"},  # Tools that accept untrusted inputs
    block_on_violation=True,  # Block or warn on violations
    enable_audit_log=True,  # Enable audit logging
)
```

### Tool Metadata

Configure tool security requirements in the `@tool` decorator:

```python
@tool(
    description="...",
    approval_mode="always_require",  # Standard human approval for this specific tool
    additional_properties={
        "confidentiality": "private",  # Tool's confidentiality level
        "accepts_untrusted": True,  # Explicitly allow untrusted inputs
        # Optional: source_integrity is ONLY needed for tools returning data without per-item labels
        # Do NOT use for action/sink tools (send_email, delete_file) - they don't produce data
        "source_integrity": "untrusted",  # Fallback for unlabeled results
    }
)
```

**Approval model:**
- Use `approval_mode="always_require"` for normal human-in-the-loop approval on a specific tool.
- Use `SecureAgentConfig(..., approval_on_violation=True)` to request approval only when a secure-policy check would otherwise block a call.

**When to use `source_integrity`:**
- ✅ Tools returning data WITHOUT embedded per-item labels
- ✅ Simple tools returning a single value (string, number)
- ❌ Tools with per-item labels (use embedded labels instead)
- ❌ Action tools (send_email, delete_file) - they don't produce meaningful data

## Best Practices

1. **Use SecureAgentConfig as a context provider**: Add `context_providers=[config]` for automatic security setup — no manual middleware, tools, or instruction wiring
2. **Use `list[Content]` with `Content.from_text()` for mixed-trust data**: When a tool returns both trusted and untrusted items (like emails), embed labels using `Content.from_text(text, additional_properties={"security_label": {...}})`
3. **Don't use source_integrity for action tools**: Tools like `send_email` or `delete_file` are sinks, not data sources - their results inherit labels from inputs
4. **Always use middleware stack**: Enable both label tracking and policy enforcement
5. **Enable automatic hiding**: Keep `auto_hide_untrusted=True` (default) for automatic protection
6. **Add security tools to agents**: Include `quarantined_llm` and `inspect_variable` in your agent's tools
7. **Add security instructions**: Use `SECURITY_TOOL_INSTRUCTIONS` or `config.get_instructions()` to teach agents how to handle hidden content
8. **Configure tool permissions**: Mark which tools can accept untrusted inputs
9. **Use variable_ids**: Prefer passing `variable_ids` to `quarantined_llm` over raw content
10. **Process in quarantine**: Use `quarantined_llm` for untrusted data processing
11. **Review audit logs**: Regularly check for policy violations
12. **Minimize inspection**: Only use `inspect_variable` when absolutely necessary
13. **Test security policies**: Verify tool permission configurations work as expected

## Audit and Compliance

### Audit Log

Access the audit log:

```python
audit_log = policy_enforcer.get_audit_log()

for violation in audit_log:
    print(f"Type: {violation['type']}")
    print(f"Function: {violation['function']}")
    print(f"Label: {violation['label']}")
    print(f"Turn: {violation['turn']}")
```

### Inspection Logging

All `inspect_variable` calls are logged with:
- Variable name
- Timestamp
- Reason for inspection (if provided)
- Security label of content

### Variable Store Access

Access the middleware's variable store to list or inspect stored variables:

```python
# Get all stored variables
variables = label_tracker.list_variables()
print(f"Stored variables: {variables}")

# Get variable metadata
metadata = label_tracker.get_variable_metadata()
for var_name, label in metadata.items():
    print(f"{var_name}: {label.integrity}/{label.confidentiality}")
```

## Testing

Run the example:

```bash
python examples/prompt_injection_defense_example.py
```

This demonstrates:
- Basic defense setup with automatic hiding
- Automatic variable indirection for UNTRUSTED content
- Quarantined LLM usage
- Variable inspection
- Policy enforcement
- Complete secure workflow

## Key Takeaways

🎯 **Easy Setup**: Use `SecureAgentConfig` as a context provider — just add `context_providers=[config]`

🤖 **Agent-Aware**: Security tools, instructions, and middleware injected automatically via `before_run()`

🔒 **Automatic Protection**: UNTRUSTED content is automatically hidden using variable indirection

🏷️ **Per-Item Labels**: Tools returning mixed-trust data can embed labels on individual items

🛡️ **Policy Enforcement**: Violations are blocked before they can cause harm

📝 **Full Auditability**: All security events are logged for compliance

🚀 **Developer Friendly**: No manual variable management needed

## API Reference

### Imports

```python
from agent_framework.security import (
    # Labels
    ContentLabel,
    IntegrityLabel,
    ConfidentialityLabel,
    combine_labels,

    # Variable Store
    ContentVariableStore,
    VariableReferenceContent,
    store_untrusted_content,

    # Message-Level Tracking (Phase 1)
    LabeledMessage,

    # Middleware
    LabelTrackingFunctionMiddleware,
    PolicyEnforcementFunctionMiddleware,

    # Security Tools
    quarantined_llm,
    get_security_tools,

    # Agent Configuration
    SecureAgentConfig,
    SECURITY_TOOL_INSTRUCTIONS,
)
from agent_framework.security import inspect_variable
```

### LabeledMessage (Phase 1)

```python
msg = LabeledMessage(
    role: str,                                # "user", "assistant", "system", "tool"
    content: Any,                             # Message content
    security_label: ContentLabel = None,      # Auto-inferred from role if None
    message_index: int = None,                # Index in conversation
    source_labels: List[ContentLabel] = None, # Labels that contributed to this message
    metadata: Dict[str, Any] = None,
)

# Methods
msg.is_trusted() -> bool                      # Check if message is trusted
msg.to_dict() -> Dict[str, Any]               # Serialize
LabeledMessage.from_dict(data) -> LabeledMessage  # Deserialize
LabeledMessage.from_message(msg, index) -> LabeledMessage  # Wrap standard message
```

### SecureAgentConfig

```python
config = SecureAgentConfig(
    auto_hide_untrusted: bool = True,         # Auto-hide UNTRUSTED content
    hide_threshold: IntegrityLabel = UNTRUSTED,  # Threshold for hiding
    allow_untrusted_tools: Set[str] = None,   # Tools that accept untrusted input
    block_on_violation: bool = True,          # Block or warn on policy violations
    enable_audit_log: bool = True,            # Enable audit logging
)

# Methods
config.get_tools() -> List[FunctionTool]      # Returns [quarantined_llm, inspect_variable]
config.get_instructions() -> str              # Returns SECURITY_TOOL_INSTRUCTIONS
config.get_middleware() -> List[FunctionMiddleware]  # Returns configured middleware
```

### quarantined_llm

```python
result = await quarantined_llm(
    prompt: str,                              # Prompt for the quarantined LLM
    variable_ids: List[str] = [],             # Variable IDs to retrieve from store
    labelled_data: Dict[str, Any] = {},       # Alternative: direct labeled data
    metadata: Dict[str, Any] = None,          # Optional metadata
) -> Dict[str, Any]

# Returns:
# {
#     "response": str,           # LLM response
#     "security_label": dict,    # Combined label of all inputs
#     "quarantined": True,
#     "variables_processed": List[str],
#     "content_summary": List[str],
# }
#
# Note: The middleware automatically hides UNTRUSTED results behind a
# VariableReferenceContent via the tool's source_integrity="untrusted"
# declaration. The agent sees a variable reference, not raw content.
```

### inspect_variable

```python
from agent_framework.security import inspect_variable


async def inspect_content() -> None:
    result = await inspect_variable(
        variable_id="var_abc123",  # ID of variable to inspect
        reason="Need to inspect hidden content",  # Reason for inspection (audit)
    )
    print(result)

# Example return:
# {
#     "variable_id": str,
#     "content": Any,            # The actual hidden content
#     "security_label": dict,
#     "warning": str,            # Security warning
# }
```

## Future Enhancements

Potential improvements:

1. **Per-session variable stores**: Isolate variables by conversation/session
2. ~~**Automatic label propagation**: Track labels through all message types and agent state~~ ✅ IMPLEMENTED (Phase 1 & 2)
3. **Fine-grained policies**: More complex policy rules (e.g., based on user roles, time-based)
4. **Integration with IAM**: Connect confidentiality labels to identity/permission systems
5. **Cryptographic isolation**: Encrypt stored variables for additional protection
6. **Variable lifetime management**: Auto-expire or garbage collect old variables
7. ~~**Cross-turn tracking**: Maintain label consistency across multiple agent turns~~ ✅ IMPLEMENTED (Context Label Tracking)
8. **Real quarantined LLM**: Implement actual isolated LLM context

## References

- [ADR-0007: Agent Filtering Middleware](../../../../docs/decisions/0007-agent-filtering-middleware.md)
- [Security Module](../../../packages/core/agent_framework/security.py) — All security primitives, middleware, tools, and configuration
