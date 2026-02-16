# Safety Evaluation with Agent Framework

This sample demonstrates how to use `Microsoft.Extensions.AI.Evaluation.Safety` to evaluate the safety of Agent Framework agent responses using Azure AI Foundry's content safety evaluators.

## What this sample demonstrates

- Creating a financial advisor agent with specific safety instructions
- Using `ContentHarmEvaluator` for comprehensive content safety assessment (Violence, HateAndUnfairness, Sexual, SelfHarm)
- Using individual safety evaluators (`ViolenceEvaluator`, `HateAndUnfairnessEvaluator`, `SelfHarmEvaluator`, `SexualEvaluator`, `ProtectedMaterialEvaluator`, `IndirectAttackEvaluator`)
- Composing multiple evaluators with `CompositeEvaluator`
- Interpreting evaluation results (scores, ratings, pass/fail)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure AI Foundry project (hub and project created)
- Azure OpenAI deployment (e.g., gpt-4o or gpt-4o-mini)
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

### Azure Resources Required

1. **Azure AI Hub and Project**: Create these in the Azure Portal
   - Follow: https://learn.microsoft.com/azure/ai-foundry/how-to/create-projects
2. **Azure OpenAI Deployment**: Deploy a model (e.g., gpt-4o or gpt-4o-mini)
3. **Azure CLI**: Install and authenticate with `az login`

### Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-project.api.azureml.ms" # Replace with your Azure Foundry project endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the FoundryAgents/Evaluation directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents/FoundryAgents_Evaluations_Step01_RedTeaming
dotnet run
```

## Expected behavior

The sample will:

1. Create a financial advisor agent with safety instructions
2. Configure `ContentSafetyServiceConfiguration` to connect to Azure AI Foundry Evaluation service
3. Run `ContentHarmEvaluator` against multiple test prompts (including an adversarial one)
4. Run individual safety evaluators (`ViolenceEvaluator`, `HateAndUnfairnessEvaluator`, etc.) with `CompositeEvaluator`
5. Display per-metric scores, ratings, and pass/fail status
6. Clean up resources by deleting the test agent

## Understanding the Results

### Content Harm Metrics (Numeric, 0-7 scale)
- **Violence**: Detects violent content in the response
- **Hate And Unfairness**: Detects hate speech or unfair content
- **Sexual**: Detects sexual content
- **Self Harm**: Detects self-harm related content

Lower scores indicate safer content. A score of 0 means no harmful content detected.

### Boolean Metrics
- **Protected Material**: Whether the response contains protected/copyrighted material (false = safe)
- **Indirect Attack**: Whether the response indicates an indirect attack (false = safe)

### Ratings
- **Exceptional**: Content is completely safe
- **Good**: Content is safe with minimal concerns
- **Unacceptable**: Content contains harmful elements

## Best Practices

1. **Test Multiple Prompts**: Include both normal and adversarial prompts to assess robustness
2. **Use All Evaluators**: Combine `ContentHarmEvaluator` with `ProtectedMaterialEvaluator` and `IndirectAttackEvaluator`
3. **Iterate on Instructions**: Improve agent safety instructions based on evaluation results
4. **Set Thresholds**: Define acceptable safety scores for your use case
5. **CI/CD Integration**: Integrate safety evaluation into your deployment pipeline

## Related Resources

- [Microsoft.Extensions.AI.Evaluation Libraries](https://learn.microsoft.com/dotnet/ai/evaluation/libraries)
- [Azure AI Foundry Evaluation Service](https://learn.microsoft.com/azure/ai-foundry/how-to/develop/evaluate-sdk)
- [Risk and Safety Evaluations](https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-metrics-built-in#risk-and-safety-evaluators)

## Next Steps

After running safety evaluations:
1. Implement agent improvements based on findings
2. Explore the Self-Reflection sample (FoundryAgents_Evaluations_Step02_SelfReflection) for quality assessment
3. Set up continuous evaluation in your CI/CD pipeline
