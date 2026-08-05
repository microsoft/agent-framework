# Skills Auto-Approval Sample

This sample demonstrates how to configure **auto-approval rules** for skill tools using the `UseToolApproval` middleware and `AgentSkillsProvider`'s built-in approval rules.

It builds on the [file-based skills sample](../Agent_Step01_FileBasedSkills/) by adding `ToolApprovalAgent` middleware that auto-approves read-only skill operations while still prompting for script execution.

## What it demonstrates

- All tools exposed by `AgentSkillsProvider` (`load_skill`, `read_skill_resource`, `run_skill_script`) always require approval by default
- Multiple ways to configure auto-approval (see below)
- Handling approval prompts for script execution via `ToolApprovalRequestContent`

## Configuring Auto-Approval

Auto-approval rules are passed to `ToolApprovalAgentOptions.AutoApprovalRules` when calling `UseToolApproval`. Rules are evaluated in order; the first rule returning `true` auto-approves the call.

### Option 1: Built-in read-only rule

Auto-approves `load_skill` and `read_skill_resource` while still prompting for `run_skill_script`:

```csharp
.UseToolApproval(new ToolApprovalAgentOptions
{
    AutoApprovalRules = [AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule],
})
```

### Option 2: Built-in all-tools rule

Auto-approves all three skill tools without prompting:

```csharp
.UseToolApproval(new ToolApprovalAgentOptions
{
    AutoApprovalRules = [AgentSkillsProvider.AllToolsAutoApprovalRule],
})
```

### Option 3: Custom lambda rule

Provide your own logic as a `Func<FunctionCallContent, ValueTask<bool>>`. For example, to auto-approve only `load_skill`:

```csharp
.UseToolApproval(new ToolApprovalAgentOptions
{
    AutoApprovalRules =
    [
        (FunctionCallContent functionCall) =>
            new ValueTask<bool>(functionCall.Name == AgentSkillsProvider.LoadSkillToolName),
    ],
})
```

### Combining rules from multiple providers

When using multiple providers (e.g., skills + file access), combine their rules in a single list:

```csharp
.UseToolApproval(new ToolApprovalAgentOptions
{
    AutoApprovalRules =
    [
        AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule,
        FileAccessProvider.ReadOnlyToolsAutoApprovalRule,
    ],
})
```

## ⚠️ Security: avoid tool-name collisions

Built-in auto-approval rules match tool calls **solely by tool name**. A rule cannot tell the
provider's own tool apart from any other registered tool that happens to share the same name. If a
different tool — especially one with a caller-configurable name, such as the Harness shell tool
(`HarnessAgentOptions.ShellToolName`) — is registered under a name that one of these rules approves
(e.g. `load_skill`, `read_skill_resource`, `run_skill_script`, or the `file_access_*` names), that
tool will be **silently auto-approved**, bypassing the human approval boundary.

When using auto-approval rules, ensure no other tool's name collides with the reserved names the
rules approve, and never assign a configurable tool name that matches one of them.

## Skills Included

### unit-converter

Converts between common units (miles↔km, pounds↔kg) using a multiplication factor.

- `references/conversion-table.md` — Conversion factor table
- `scripts/convert.py` — Python script that performs the conversion

## Running the Sample

### Prerequisites

- .NET 10.0 SDK
- Azure OpenAI endpoint with a deployed model
- Python 3 installed and available as `python3` on your PATH

### Setup

```bash
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"
```

### Run

```bash
dotnet run
```

### Expected Behavior

- `load_skill` and `read_skill_resource` calls are auto-approved (no user prompt)
- `run_skill_script` calls prompt the user for approval before executing
