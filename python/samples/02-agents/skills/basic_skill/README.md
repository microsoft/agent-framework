# Agent Skills Sample

This sample demonstrates how to use **Agent Skills** with a `FileAgentSkillsProvider` in the Microsoft Agent Framework.

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
basic_skills/
├── basic_file_skills.py
├── README.md
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
- An [Azure AI Foundry](https://ai.azure.com/) project with a deployed model (e.g. `gpt-4o-mini`)

### Environment Variables

Set the required environment variables in a `.env` file (see `python/.env.example`):

- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your model deployment (defaults to `gpt-4o-mini`)

### Authentication

This sample uses `AzureCliCredential` for authentication. Run `az login` in your terminal before running the sample.

### Run

```bash
cd python
uv run samples/02-agents/skills/basic_skills/basic_file_skills.py
```

### Examples

The sample runs two examples:

1. **Expense policy FAQ** — Asks about tip reimbursement; the agent loads the expense-report skill and reads the FAQ resource
2. **Filing an expense report** — Multi-turn conversation to draft an expense report using the template asset

## Learn More

- [Agent Skills Specification](https://agentskills.io/)
- [Microsoft Agent Framework Documentation](../../../../../docs/)
