# Red Teaming with Azure AI Foundry (Classic)

> [!IMPORTANT]
> This sample uses the **classic Azure AI Foundry** red teaming API (`/redTeams/runs`) via `Azure.AI.Projects`. Results are viewable in the classic Foundry portal experience. The **new Foundry** portal's red teaming feature uses a different evaluation-based API that is not yet available in the .NET SDK.

This sample demonstrates how to use Azure AI Foundry's Red Teaming service to assess the safety and resilience of an AI model against adversarial attacks.

## What this sample demonstrates

- Configuring a red team run targeting an Azure OpenAI model deployment
- Using multiple `AttackStrategy` options (Easy, Moderate, Jailbreak)
- Evaluating across `RiskCategory` categories (Violence, HateUnfairness, Sexual, SelfHarm)
- Submitting a red team scan and polling for completion
- Reviewing results in the Azure AI Foundry portal

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure AI Foundry project (hub and project created)
- Azure OpenAI deployment (e.g., gpt-4o or gpt-4o-mini)
- Azure CLI installed and authenticated (for Azure credential authentication)

### Regional Requirements

Red teaming is only available in regions that support risk and safety evaluators:
- **East US 2**, **Sweden Central**, **US North Central**, **France Central**, **Switzerland West**

### Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project" # Replace with your Azure Foundry project endpoint
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents/FoundryAgents_Evaluations_Step01_RedTeaming
dotnet run
```

## Expected behavior

The sample will:

1. Configure a `RedTeam` run targeting the specified model deployment
2. Define risk categories and attack strategies
3. Submit the scan to Azure AI Foundry's Red Teaming service
4. Poll for completion (this may take several minutes)
5. Display the run status and direct you to the Azure AI Foundry portal for detailed results

## Understanding Red Teaming

### Attack Strategies

| Strategy | Description |
|----------|-------------|
| Easy | Simple encoding/obfuscation attacks (ROT13, Leetspeak, etc.) |
| Moderate | Moderate complexity attacks requiring an LLM for orchestration |
| Jailbreak | Crafted prompts designed to bypass AI safeguards (UPIA) |

### Risk Categories

| Category | Description |
|----------|-------------|
| Violence | Content related to violence |
| HateUnfairness | Hate speech or unfair content |
| Sexual | Sexual content |
| SelfHarm | Self-harm related content |

### Interpreting Results

- Results are available in the Azure AI Foundry portal (**classic view** — toggle at top-right) under the red teaming section
- Lower Attack Success Rate (ASR) is better — target ASR < 5% for production
- Review individual attack conversations to understand vulnerabilities

### Current Limitations

> [!NOTE]
> - The .NET Red Teaming API (`Azure.AI.Projects`) currently supports targeting **model deployments only** via `AzureOpenAIModelConfiguration`. The `AzureAIAgentTarget` type exists in the SDK but is consumed by the **Evaluation Taxonomy** API (`/evaluationtaxonomies`), not by the Red Teaming API (`/redTeams/runs`).
> - Agent-targeted red teaming with agent-specific risk categories (Prohibited actions, Sensitive data leakage, Task adherence) is documented in the [concept docs](https://learn.microsoft.com/azure/ai-foundry/concepts/ai-red-teaming-agent) but is not yet available via the public REST API or .NET SDK.
> - Results from this API appear in the **classic** Azure AI Foundry portal view. The new Foundry portal uses a separate evaluation-based system with `eval_*` identifiers.

## Related Resources

- [Azure AI Red Teaming Agent](https://learn.microsoft.com/azure/ai-foundry/concepts/ai-red-teaming-agent)
- [RedTeam .NET API Reference](https://learn.microsoft.com/dotnet/api/azure.ai.projects.redteam?view=azure-dotnet-preview)
- [Risk and Safety Evaluations](https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-metrics-built-in#risk-and-safety-evaluators)

## Next Steps

After running red teaming:
1. Review attack results and strengthen agent guardrails
2. Explore the Self-Reflection sample (FoundryAgents_Evaluations_Step02_SelfReflection) for quality assessment
3. Set up continuous red teaming in your CI/CD pipeline
