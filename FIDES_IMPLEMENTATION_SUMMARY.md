# FIDES Implementation Summary

## Overview

**FIDES**  is a comprehensive deterministic prompt injection defense system for the agent framework. The implementation provides label-based security mechanisms to defend against prompt injection attacks by tracking integrity and confidentiality of content throughout agent execution.

**🚀 Key Features:**
- **Automatic Variable Hiding** - UNTRUSTED content is automatically hidden without requiring manual intervention
- **Per-Item Embedded Labels** - Tools can return mixed-trust data with security labels on individual items
- **SecureAgentConfig** - One-line secure agent configuration with tools, instructions, and middleware
- **Data Exfiltration Prevention** - `max_allowed_confidentiality` prevents sensitive data leakage
- **Message-Level Label Tracking** (Phase 1) - Track labels on every message in the conversation
- **Content Lineage Tracking** (Phase 2) - Track how content is derived and transformed

## Architecture Components

The FIDES defense system consists of eight main components:

1. **Content Labeling Infrastructure** - Labels for tracking integrity and confidentiality
2. **Label Tracking Middleware** - Automatically assigns, propagates labels, and hides untrusted content
3. **Per-Item Embedded Labels** - Tools can return mixed-trust data with per-item security labels
4. **Policy Enforcement Middleware** - Blocks tool calls that violate security policies
5. **Security Tools** - Specialized tools for safe handling of untrusted content (`quarantined_llm`, `inspect_variable`)
6. **SecureAgentConfig** - Helper class for easy secure agent configuration
7. **Message-Level Label Tracking** - Track labels on every message in the conversation (Phase 1)
8. **Content Lineage Tracking** - Track how content is derived and transformed (Phase 2)

## Implementation Details

### Files Created

1. **`_security.py`** (~400+ lines)
   - `IntegrityLabel` enum (TRUSTED/UNTRUSTED)
   - `ConfidentialityLabel` enum (PUBLIC/PRIVATE/USER_IDENTITY)
   - `ContentLabel` class with serialization support
   - `combine_labels()` function for label composition
   - `ContentVariableStore` for client-side content storage
   - `VariableReferenceContent` for variable indirection
   - `LabeledMessage` class for message-level tracking (Phase 1)
   - `ContentLineage` class for lineage tracking (Phase 2)
   - `check_confidentiality_allowed()` helper for data exfiltration prevention

2. **`_security_middleware.py`** (~600+ lines)
   - `LabelTrackingFunctionMiddleware` - Tracks and propagates security labels
     - Automatic variable hiding (`auto_hide_untrusted` flag)
     - Per-middleware `ContentVariableStore` instance
     - Thread-local storage for tool access
     - Context-level label tracking (`get_context_label()`, `reset_context_label()`)
     - Per-item embedded label processing
     - Message-level tracking (`label_message()`, `label_messages()`, `get_all_message_labels()`)
     - Content lineage tracking (`track_lineage()`, `get_lineage()`, `get_all_lineage()`)
   - `PolicyEnforcementFunctionMiddleware` - Enforces security policies
     - Uses context label for policy decisions
     - Data exfiltration prevention via `max_allowed_confidentiality`
     - Audit log for all violations

3. **`_security_tools.py`** (~400+ lines)
   - `quarantined_llm()` - Isolated LLM calls with labeled data
     - Supports `variable_ids` parameter for referencing hidden content
     - `auto_hide_result` parameter for automatic result hiding
     - Content lineage tracking integration
     - Supports `quarantine_chat_client` for real LLM calls
   - `inspect_variable()` - Controlled variable content inspection
     - Thread-local middleware access
     - Prefers middleware's variable store over global
   - `store_untrusted_content()` - Helper for manual variable indirection (legacy)
   - `get_security_tools()` - Returns list of security tools
   - Helper functions for variable store management

4. **`_security_config.py`** (~200+ lines)
   - `SecureAgentConfig` - Helper class for easy secure agent configuration
     - `get_tools()` - Returns `[quarantined_llm, inspect_variable]`
     - `get_instructions()` - Returns `SECURITY_TOOL_INSTRUCTIONS`
     - `get_middleware()` - Returns configured middleware stack
     - `get_quarantine_client()` - Returns quarantine chat client
   - `SECURITY_TOOL_INSTRUCTIONS` - Detailed guidance for agents on handling hidden content

5. **`FIDES_DEVELOPER_GUIDE.md`** (~1250 lines)
   - Complete documentation of the FIDES security system
   - Architecture overview and design rationale
   - Usage examples (6+ comprehensive scenarios)
   - Best practices and configuration options
   - API reference with full parameter documentation
   - Data exfiltration prevention documentation

6. **`tests/test_security.py`** (~800+ lines)
   - Unit tests for ContentLabel and label operations
   - Tests for ContentVariableStore functionality
   - Tests for VariableReferenceContent
   - Middleware behavior tests (label tracking and policy enforcement)
   - Automatic hiding tests
   - Per-item embedded label tests
   - Context label tracking tests
   - Message-level tracking tests (Phase 1)
   - Content lineage tests (Phase 2)
   - Data exfiltration prevention tests

7. **`docs/decisions/0011-prompt-injection-defense.md`**
   - Architecture Decision Record (ADR)
   - Design rationale and alternatives considered
   - Security properties and guarantees

8. **`QUICK_START_FIDES.md`**
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

Tools returning mixed-trust data can embed labels on individual items:

```python
@ai_function(description="Fetch emails from inbox")
async def fetch_emails(count: int = 5) -> list[dict]:
    return [
        {
            "id": email["id"],
            "body": email["body"],
            "additional_properties": {
                "security_label": {
                    "integrity": "trusted" if email["is_internal"] else "untrusted",
                    "confidentiality": "private",
                }
            },
        }
        for email in emails
    ]
```

### 3. Automatic Variable Hiding

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
@ai_function(
    description="Post to public Slack channel",
    additional_properties={
        "max_allowed_confidentiality": "public",  # Blocks PRIVATE data
    }
)
async def post_to_slack(channel: str, message: str) -> dict:
    return {"status": "posted"}
```

### 6. SecureAgentConfig

One-line secure agent configuration:

```python
config = SecureAgentConfig(
    auto_hide_untrusted=True,
    allow_untrusted_tools={"search_web", "fetch_data"},
    block_on_violation=True,
    quarantine_chat_client=quarantine_client,  # Optional: real LLM for quarantine
)

agent = ChatAgent(
    chat_client=client,
    name="secure_assistant",
    instructions=base_instructions + config.get_instructions(),
    tools=[my_tool, *config.get_tools()],
    middleware=config.get_middleware(),
)
```

### 7. Message-Level Label Tracking (Phase 1)

Track security labels at the message level:

```python
labeled_messages = middleware.label_messages(messages)
label = middleware.get_message_label(5)
all_labels = middleware.get_all_message_labels()
```

### 8. Content Lineage Tracking (Phase 2)

Track how content is derived and transformed:

```python
lineage = middleware.track_lineage(
    content_id="summary_123",
    derived_from=["var_abc", "var_def"],
    transformation="llm_summary",
    combined_label=combined_label,
)
```

## Security Properties

### Deterministic Defense

1. **Always labeling**: Every tool call receives a label
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

### Recommended: SecureAgentConfig

```python
from agent_framework import SecureAgentConfig

config = SecureAgentConfig(
    auto_hide_untrusted=True,
    allow_untrusted_tools={"search_web"},
    block_on_violation=True,
)

agent = ChatAgent(
    chat_client=client,
    name="secure_assistant",
    instructions=f"You are helpful.\n\n{config.get_instructions()}",
    tools=[search_web, *config.get_tools()],
    middleware=config.get_middleware(),
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
- 40+ unit tests covering all components
- Label creation, serialization, combination
- Variable store operations
- Middleware behavior (tracking and enforcement)
- Automatic hiding with per-item labels
- Context label tracking
- Message-level tracking (Phase 1)
- Content lineage tracking (Phase 2)
- Data exfiltration prevention
- Policy violation scenarios
- Audit log verification

Run tests:
```bash
pytest tests/test_security.py -v
```

## Code Statistics

- **Total lines**: ~4,000+ lines
- **New modules**: 4+ (`_security.py`, `_security_middleware.py`, `_security_tools.py`, `_security_config.py`)
- **Total tests**: 40+ unit tests
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
✅ One-line secure agent configuration
✅ `get_tools()`, `get_instructions()`, `get_middleware()` methods
✅ `quarantine_chat_client` support for real LLM calls
✅ `SECURITY_TOOL_INSTRUCTIONS` constant

### Phase 1: Message-Level Tracking
✅ `LabeledMessage` class with auto-inference from role
✅ `label_message()`, `get_message_label()`, `label_messages()` methods
✅ `get_all_message_labels()` method

### Phase 2: Content Lineage Tracking
✅ `ContentLineage` class for tracking derivation
✅ `track_lineage()`, `get_lineage()`, `get_all_lineage()` methods
✅ Integration with `quarantined_llm` auto-hiding

### Documentation & Testing
✅ Complete FIDES Developer Guide (~1250 lines)
✅ Architecture Decision Record (ADR)
✅ Quick Start Guide
✅ Comprehensive test suite (40+ tests)
✅ Example code with 6+ scenarios

## Summary

**FIDES** provides a comprehensive, deterministic defense against prompt injection attacks with:

- **Zero-effort protection**: Automatic variable hiding for developers
- **Granular control**: Per-item embedded labels for mixed-trust data
- **Easy configuration**: `SecureAgentConfig` for one-line setup
- **Data safety**: Exfiltration prevention via confidentiality gates
- **Full traceability**: Message-level and content lineage tracking
- **Complete auditability**: All security events logged

The system ensures that untrusted content never directly reaches the LLM context and that all tool calls are policy-checked based on the cumulative security state before execution.
