# FIDES Implementation Summary

## Overview

**FIDES**  is a comprehensive deterministic prompt injection defense system for the agent framework. The implementation provides label-based security mechanisms to defend against prompt injection attacks by tracking integrity and confidentiality of content throughout agent execution.

**🚀 Key Features:**
- **Context Provider Pattern** - `SecureAgentConfig` extends `ContextProvider`, injecting tools, instructions, and middleware automatically
- **Automatic Variable Hiding** - UNTRUSTED content is automatically hidden without requiring manual intervention
- **Per-Item Embedded Labels** - Tools return `list[Content]` with `Content.from_text()` for proper label propagation
- **SecureAgentConfig** - One-line secure agent configuration via `context_providers=[config]`
- **Data Exfiltration Prevention** - `max_allowed_confidentiality` prevents sensitive data leakage
- **Message-Level Label Tracking** (Phase 1) - Track labels on every message in the conversation

## Architecture Components

The FIDES defense system consists of seven main components:

1. **Content Labeling Infrastructure** - Labels for tracking integrity and confidentiality
2. **Label Tracking Middleware** - Automatically assigns, propagates labels, and hides untrusted content
3. **Per-Item Embedded Labels** - Tools can return mixed-trust data with per-item security labels
4. **Policy Enforcement Middleware** - Blocks tool calls that violate security policies
5. **Security Tools** - Specialized tools for safe handling of untrusted content (`quarantined_llm`, `inspect_variable`)
6. **SecureAgentConfig** - Context provider for easy secure agent configuration
7. **Message-Level Label Tracking** - Track labels on every message in the conversation (Phase 1)

## Implementation Details

### Files Created

1. **`_security.py`** (~2950 lines — all security primitives, middleware, tools, and configuration in a single module)
   - `IntegrityLabel` enum (TRUSTED/UNTRUSTED)
   - `ConfidentialityLabel` enum (PUBLIC/PRIVATE/USER_IDENTITY)
   - `ContentLabel` class with serialization support
   - `combine_labels()` function for label composition
   - `ContentVariableStore` for client-side content storage
   - `VariableReferenceContent` for variable indirection
   - `LabeledMessage` class (inherits from `Message`) for message-level tracking
   - `check_confidentiality_allowed()` helper for data exfiltration prevention
   - `LabelTrackingFunctionMiddleware` - Tracks and propagates security labels
   - `PolicyEnforcementFunctionMiddleware` - Enforces security policies
   - `SecureAgentConfig` extends `ContextProvider` - automatic secure agent configuration
   - `quarantined_llm()` - Isolated LLM calls with labeled data
   - `inspect_variable()` - Controlled variable content inspection
   - `store_untrusted_content()` - Helper for manual variable indirection (legacy)
   - `get_security_tools()` - Returns list of security tools
   - `SECURITY_TOOL_INSTRUCTIONS` - Detailed guidance for agents


2. **`FIDES_DEVELOPER_GUIDE.md`** (~1250 lines)
   - Located at `python/samples/02-agents/security/FIDES_DEVELOPER_GUIDE.md`
   - Complete documentation of the FIDES security system
   - Architecture overview and design rationale
   - Usage examples (6+ comprehensive scenarios)
   - Best practices and configuration options
   - API reference with full parameter documentation
   - Data exfiltration prevention documentation

3. **`tests/test_security.py`** (~800+ lines)
   - Unit tests for ContentLabel and label operations
   - Tests for ContentVariableStore functionality
   - Tests for VariableReferenceContent
   - Middleware behavior tests (label tracking and policy enforcement)
   - Automatic hiding tests
   - Per-item embedded label tests
   - Context label tracking tests
   - Message-level tracking tests (Phase 1)
   - Data exfiltration prevention tests

4. **`docs/decisions/0024-prompt-injection-defense.md`**
   - Architecture Decision Record (ADR)
   - Design rationale and alternatives considered
   - Security properties and guarantees

5. **`python/samples/02-agents/security/README.md`** (was `QUICK_START_FIDES.md`)
   - Quick reference guide for FIDES security features
   - Common patterns and troubleshooting

### Files Modified

1. **`__init__.py`**
   - Added exports for security modules

## Core Features

### 1. Content Labeling Infrastructure

- **IntegrityLabel**: TRUSTED (user input) vs UNTRUSTED (AI-generated, external)
- **ConfidentialityLabel**: PUBLIC, PRIVATE, USER_IDENTITY
- **Label Combination**: Most restrictive policy (UNTRUSTED + metadata merging)
- **Serialization**: Full support for `to_dict()` and `from_dict()`

### 2. Per-Item Embedded Labels

Tools returning mixed-trust data embed labels on individual items using `Content.from_text()`:

```python
import json
from agent_framework import Content, tool

@tool(description="Fetch emails from inbox")
async def fetch_emails(count: int = 5) -> list[Content]:
    return [
        Content.from_text(
            json.dumps({
                "id": email["id"],
                "body": email["body"],
            }),
            additional_properties={
                "security_label": {
                    "integrity": "trusted" if email["internal"] else "untrusted",
                    "confidentiality": "private",
                }
            ),
        )
        for email in emails
    ]
```

These embedded labels are automatically consumed by `LabelTrackingFunctionMiddleware`, which:
- Extracts the `security_label` from `additional_properties`
- Uses the embedded label as the highest-priority source for that item
- Automatically hides UNTRUSTED items in the variable store
- Replaces hidden items with `VariableReferenceContent` in the LLM context
- Preserves TRUSTED items visible to the LLM without tainting the context label

This enables tools to return mixed-trust data where some items (internal emails) remain visible while untrusted items (external emails) are automatically hidden without manual intervention.
           },
        )
        for email in emails
    ]
```

### 3. Automatic Variable Hiding

This feature automatically hides any UNTRUSTED content returned by tools while keeping the hiding logic transparent to the developer. Developers do not need to manually call `store_untrusted_content()`. This allows the LLM /agent's context to remain clean and secure. Key aspects include:

- **Automatic Detection**: Middleware checks integrity label after each tool call
- **Automatic Storage**: UNTRUSTED results/items stored in variable store
- **Transparent Replacement**: LLM context receives `VariableReferenceContent`
- **Context Label Protection**: Hidden content does NOT taint context label

### 4. Context Label Tracking

- Context label starts as TRUSTED + PUBLIC
- Gets updated (tainted) when non-hidden untrusted content enters context
- Policy enforcement uses context label for validation
- Provides `get_context_label()` and `reset_context_label()` methods

### 5. Data Exfiltration Prevention

Tools declare `max_allowed_confidentiality` to prevent sensitive data leakage:

```python
@tool(
    description="Post to public Slack channel",
    additional_properties={
        "max_allowed_confidentiality": "public",  # Blocks PRIVATE data
    }
)
async def post_to_slack(channel: str, message: str) -> dict:
    return {"status": "posted"}
```

### 6. SecureAgentConfig (Context Provider)

SecureAgentConfig extends `ContextProvider` for automatic secure agent configuration:

```python
config = SecureAgentConfig(
    auto_hide_untrusted=True,
    allow_untrusted_tools={"search_web", "fetch_data"},
    block_on_violation=True,
    quarantine_chat_client=quarantine_client,  # Optional: real LLM for quarantine
)

# Context provider injects tools, instructions, and middleware automatically
agent = Agent(
    client=client,
    name="secure_assistant",
    instructions="You are a helpful assistant.",
    tools=[my_tool],
    context_providers=[config],  # That's it!
)
```

## Security Properties

### Deterministic Defense

1. **Tiered label propagation**: Every tool result receives a label via 3-tier priority (embedded > source_integrity > input labels join)
2. **Context tracking**: Cumulative security state tracked across turns
3. **Policy enforcement**: Violations blocked before execution
4. **Content isolation**: Untrusted content stored as variables
5. **Taint propagation**: Once context becomes UNTRUSTED, it stays UNTRUSTED
6. **Data exfiltration prevention**: `max_allowed_confidentiality` gates output destinations
7. **Audit trail**: All security events logged
8. **No runtime guessing**: Deterministic label assignment

### Attack Prevention

- **Direct prompt injection**: Variables hide actual content from LLM
- **Indirect prompt injection**: Labels track untrusted AI-generated calls
- **Privilege escalation**: Policy blocks untrusted calls to privileged tools
- **Data exfiltration**: Confidentiality labels + `max_allowed_confidentiality` enforced
- **Tool misuse**: Only whitelisted tools accept untrusted inputs

## Configuration Options

### LabelTrackingFunctionMiddleware
- `default_integrity`: Default label for unknown sources
- `default_confidentiality`: Default confidentiality level
- `auto_hide_untrusted`: Enable automatic variable hiding (default: True)
- `hide_threshold`: Integrity level at which hiding occurs (default: UNTRUSTED)

### PolicyEnforcementFunctionMiddleware
- `allow_untrusted_tools`: Set of tools accepting untrusted inputs
- `block_on_violation`: Block vs warn on violations
- `enable_audit_log`: Enable/disable audit logging

### Tool Metadata (via `additional_properties`)
- `confidentiality`: Tool's output confidentiality level
- `source_integrity`: Fallback integrity for unlabeled results (data-producing tools only)
- `accepts_untrusted`: Explicit untrusted input permission
- `max_allowed_confidentiality`: Maximum allowed input confidentiality (for sink tools)
- `requires_approval`: Human-in-the-loop requirement

## Usage Pattern

### Recommended: SecureAgentConfig as Context Provider

```python
from agent_framework import SecureAgentConfig

config = SecureAgentConfig(
    auto_hide_untrusted=True,
    allow_untrusted_tools={"search_web"},
    block_on_violation=True,
)

# Context provider injects everything automatically
agent = Agent(
    client=client,
    name="secure_assistant",
    instructions="You are a helpful assistant.",
    tools=[search_web],
    context_providers=[config],  # Tools, instructions, and middleware injected via before_run()
)
```

### Processing Hidden Content with quarantined_llm

```python
# Agent automatically uses quarantined_llm with variable_ids
result = await quarantined_llm(
    prompt="Summarize this data",
    variable_ids=["var_abc123"]  # Reference hidden content by ID
)
```

## Testing

Comprehensive test suite with:
- 115+ unit tests covering all components
- Label creation, serialization, combination
- Variable store operations
- Middleware behavior (tracking and enforcement)
- Automatic hiding with per-item labels
- Context label tracking
- Message-level tracking (Phase 1)
- Data exfiltration prevention
- Policy violation scenarios
- Audit log verification

Run tests:
```bash
pytest tests/test_security.py -v
```

## Code Statistics

- **Total lines**: ~2,950+ lines (single `_security.py` module)
- **New modules**: 1 (`_security.py` — consolidated from 3 original modules)
- **Total tests**: 115+ unit tests
- **Documentation**: 1,250+ lines in developer guide
- **Examples**: 6+ comprehensive scenarios

## Deliverables Checklist

### Core Implementation
✅ ContentLabel infrastructure with integrity and confidentiality
✅ ContentVariableStore for variable indirection
✅ VariableReferenceContent for safe context references
✅ LabelTrackingFunctionMiddleware for automatic labeling
✅ PolicyEnforcementFunctionMiddleware for policy enforcement
✅ quarantined_llm tool for isolated processing
✅ inspect_variable tool for controlled content access
✅ store_untrusted_content helper for manual variable indirection

### Automatic Hiding Enhancement
✅ Auto-hide UNTRUSTED content with `auto_hide_untrusted` flag
✅ Per-middleware ContentVariableStore instances
✅ Thread-local storage for middleware access from tools
✅ Automatic UNTRUSTED content replacement

### Per-Item Embedded Labels
✅ Support for `additional_properties.security_label` on individual items
✅ Mixed-trust data handling (hide untrusted, keep trusted visible)
✅ Fallback to `source_integrity` for unlabeled items

### Context Label Tracking
✅ Cumulative context label tracking across turns
✅ Hidden content does NOT taint context
✅ `get_context_label()` and `reset_context_label()` methods
✅ Policy enforcement uses context label

### Data Exfiltration Prevention
✅ `max_allowed_confidentiality` tool property
✅ `check_confidentiality_allowed()` helper function
✅ Policy enforcement validates confidentiality flow

### SecureAgentConfig
✅ Context provider pattern with `ContextProvider` base class
✅ `before_run()` hook for automatic injection of tools, instructions, and middleware
✅ One-line secure agent configuration via `context_providers=[config]`
✅ `get_tools()`, `get_instructions()`, `get_middleware()` methods (for manual use)
✅ `quarantine_chat_client` support for real LLM calls
✅ `SECURITY_TOOL_INSTRUCTIONS` constant

### Documentation & Testing
✅ Complete FIDES Developer Guide (~1250 lines)
✅ Architecture Decision Record (ADR)
✅ Quick Start Guide
✅ Comprehensive test suite (115+ tests)
✅ Example code with 6+ scenarios
✅ 3 complete security examples (email, repo confidentiality, GitHub MCP labels)

## Summary

**FIDES** provides a comprehensive, deterministic defense against prompt injection attacks with:

- **Zero-effort protection**: Automatic variable hiding for developers
- **Context provider pattern**: `SecureAgentConfig` extends `ContextProvider` for automatic setup
- **Granular control**: Per-item embedded labels via `Content.from_text()` for mixed-trust data
- **Easy configuration**: `SecureAgentConfig` for one-line setup
- **Data safety**: Exfiltration prevention via confidentiality gates
- **Full traceability**: Message-level label tracking
- **Complete auditability**: All security events logged

The system ensures that untrusted content never directly reaches the LLM context and that all tool calls are policy-checked based on the cumulative security state before execution.
