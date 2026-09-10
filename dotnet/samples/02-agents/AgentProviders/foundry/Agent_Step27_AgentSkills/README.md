# Foundry Agent Skills

This sample demonstrates how to use Agent Skills with a `FoundryAgent` backed by a
server-side versioned agent in Microsoft Foundry.

## What this sample demonstrates

- Creating a server-side versioned Foundry agent
- Defining an Agent Skill in code with `AgentInlineSkill`
- Injecting `AgentSkillsProvider` through the `clientFactory`
- Auto-approving read-only Agent Skills operations
- Invoking the agent and cleaning up the server-side agent

## Prerequisites

- A Microsoft Foundry project
- An authenticated Azure identity (for example, sign in with `az login`)

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

## Run the sample

```powershell
dotnet run
```