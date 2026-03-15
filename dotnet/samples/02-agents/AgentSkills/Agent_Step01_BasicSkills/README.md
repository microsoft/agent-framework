# Agent Skills Sample

This sample demonstrates how to use **Agent Skills** with a `ChatClientAgent` in the Microsoft Agent Framework.

## What are Agent Skills?

Agent Skills are modular packages of instructions and resources that enable AI agents to perform specialized tasks. They follow the [Agent Skills specification](https://agentskills.io/) and implement the progressive disclosure pattern:

1. **Advertise**: Skills are advertised with name + description (~100 tokens per skill)
2. **Load**: Full instructions are loaded on-demand via `load_skill` tool
3. **Resources**: References and other files loaded via `read_skill_resource` tool

## Skills Included

### expense-report
Policy-based expense filing with spending limits, receipt requirements, and approval workflows.
- `references/POLICY_FAQ.md` — Detailed expense policy Q&A
- `assets/expense-report-template.md` — Submission template

## Project Structure

```
Agent_Step01_BasicSkills/
├── Program.cs
├── Agent_Step01_BasicSkills.csproj
└── skills/
    └── expense-report/
        ├── SKILL.md
        ├── references/
        │   └── POLICY_FAQ.md
        └── assets/
            └── expense-report-template.md
```

## Running the Sample

### Prerequisites
- .NET 10.0 SDK
- Azure OpenAI endpoint with a deployed model

### Setup
1. Set environment variables:
   ```bash
   export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
   export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
   ```

2. Run the sample:
   ```bash
   dotnet run
   ```

### Examples

The sample runs two examples:

1. **Expense policy FAQ** — Asks about tip reimbursement; the agent loads the expense-report skill and reads the FAQ resource
2. **Filing an expense report** — Multi-turn conversation to draft an expense report using the template asset

## Learn More

- [Agent Skills Specification](https://agentskills.io/)
- [Microsoft Agent Framework Documentation](../../../../../docs/)
