# Self-Reflection Evaluation with Groundedness Assessment

This sample demonstrates the self-reflection pattern using Agent Framework with `Microsoft.Extensions.AI.Evaluation.Quality` evaluators. The agent iteratively improves its responses based on real groundedness evaluation scores.

For details on the self-reflection approach, see [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366) (NeurIPS 2023).

## What this sample demonstrates

- Self-reflection loop that improves responses using real `GroundednessEvaluator` scores
- Using `RelevanceEvaluator` and `CoherenceEvaluator` for multi-metric quality assessment
- Combining quality and safety evaluators with `CompositeEvaluator`
- Configuring `ContentSafetyServiceConfiguration` for safety evaluators alongside LLM-based quality evaluators
- Tracking improvement across iterations

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
   - Agent model: Used to generate responses
   - Evaluator model: Quality evaluators use an LLM; best results with GPT-4o
3. **Azure CLI**: Install and authenticate with `az login`

### Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-project.api.azureml.ms"  # Azure Foundry project endpoint
$env:AZURE_OPENAI_ENDPOINT="https://your-openai.openai.azure.com/"         # Azure OpenAI endpoint (for quality evaluators)
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"                   # Model deployment name
```

**Note**: For best evaluation results, use GPT-4o or GPT-4o-mini as the evaluator model. The groundedness evaluator has been tested and tuned for these models.

## Run the sample

Navigate to the sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents/FoundryAgents_Evaluations_Step02_SelfReflection
dotnet run
```

## Expected behavior

The sample runs three evaluation scenarios:

### 1. Self-Reflection with Groundedness
- Asks a question with grounding context
- Evaluates response groundedness using `GroundednessEvaluator`
- If score is below 4/5, asks the agent to improve with feedback
- Repeats up to 3 iterations
- Tracks and reports the best score achieved

### 2. Quality Evaluation
- Evaluates a single response with multiple quality evaluators:
  - `RelevanceEvaluator` — is the response relevant to the question?
  - `CoherenceEvaluator` — is the response logically coherent?
  - `GroundednessEvaluator` — is the response grounded in the provided context?

### 3. Combined Quality + Safety Evaluation
- Runs both quality and safety evaluators together:
  - `RelevanceEvaluator`, `CoherenceEvaluator` (quality)
  - `ContentHarmEvaluator` (safety — violence, hate, sexual, self-harm)
  - `ProtectedMaterialEvaluator` (safety — copyrighted content detection)

## Understanding the Evaluation

### Groundedness Score (1-5 scale)

The `GroundednessEvaluator` measures how well the agent's response is grounded in the provided context:

- **5** = Excellent - Response is fully grounded in context
- **4** = Good - Mostly grounded with minor deviations
- **3** = Fair - Partially grounded but includes unsupported claims
- **2** = Poor - Significant amount of ungrounded content
- **1** = Very Poor - Response is largely unsupported by context

### Self-Reflection Process

1. **Initial Response**: Agent generates answer based on question + context
2. **Evaluation**: `GroundednessEvaluator` scores the response (1-5)
3. **Feedback**: If score < 4, agent receives the score and is asked to improve
4. **Iteration**: Process repeats until good score or max iterations

## Best Practices

1. **Provide Complete Context**: Ensure grounding context contains all information needed to answer the question
2. **Clear Instructions**: Give the agent clear instructions about staying grounded in context
3. **Use Quality Models**: GPT-4o recommended for evaluation tasks
4. **Multiple Evaluators**: Use combination of evaluators (groundedness + relevance + coherence)
5. **Batch Processing**: For production, process multiple questions in batch

## Related Resources

- [Reflexion Paper (NeurIPS 2023)](https://arxiv.org/abs/2303.11366)
- [Microsoft.Extensions.AI.Evaluation Libraries](https://learn.microsoft.com/dotnet/ai/evaluation/libraries)
- [GroundednessEvaluator API Reference](https://learn.microsoft.com/dotnet/api/microsoft.extensions.ai.evaluation.quality.groundednessevaluator)
- [Azure AI Foundry Evaluation Service](https://learn.microsoft.com/azure/ai-foundry/how-to/develop/evaluate-sdk)

## Next Steps

After running self-reflection evaluation:
1. Implement similar patterns for other quality metrics (relevance, coherence, fluency)
2. Integrate into CI/CD pipeline for continuous quality assurance
3. Explore the Safety Evaluation sample (FoundryAgents_Evaluations_Step01_RedTeaming) for content safety assessment
