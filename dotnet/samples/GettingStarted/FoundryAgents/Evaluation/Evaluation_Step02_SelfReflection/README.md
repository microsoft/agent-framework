# Self-Reflection Evaluation with Groundedness Assessment

This sample demonstrates the self-reflection pattern using Agent Framework and .NET's Groundedness Evaluator. The agent iteratively improves its responses based on groundedness evaluation scores.

For details on the self-reflection approach, see [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366) (NeurIPS 2023).

## What this sample demonstrates

- Iterative self-reflection loop that automatically improves responses based on groundedness evaluation
- Using `Microsoft.Extensions.AI.Evaluation` and `GroundednessEvaluator` for quality assessment
- Measuring how well responses are grounded in provided context
- Tracking improvement across iterations
- Best practices for achieving high-quality, contextually accurate agent responses

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
   - Evaluator model (optional): Can use separate model for evaluation or same as agent
3. **Azure CLI**: Install and authenticate with `az login`

### Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-project.api.azureml.ms" # Replace with your Azure Foundry project endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Model for the agent
$env:AZURE_FOUNDRY_EVALUATOR_DEPLOYMENT_NAME="gpt-4o"     # Optional: Model for evaluation (defaults to same as agent)
```

**Note**: For best evaluation results, use GPT-4o or GPT-4o-mini as the evaluator model. The groundedness evaluator has been tested and tuned for these models.

## Run the sample

Navigate to the FoundryAgents/Evaluation directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents/Evaluation
dotnet run --project .\Evaluation_Step02_SelfReflection
```

## Expected behavior

The sample will:

1. Create a knowledge agent with instructions to answer accurately based on context
2. Ask a question about Azure AI Foundry benefits
3. Provide grounding context with the correct information
4. Run a self-reflection loop (up to 3 iterations):
   - Generate initial response
   - Evaluate groundedness (score 1-5)
   - If score < 5, provide feedback and request improvement
   - Repeat until perfect score (5) or max iterations reached
5. Display the best response and score achieved
6. Clean up resources

### Example Output

```
SELF-REFLECTION EVALUATION WITH GROUNDEDNESS ASSESSMENT
===============================================================================

Created agent: KnowledgeAgent

Question:
What are the main benefits of using Azure AI Foundry for building AI applications?

Grounding Context:
Azure AI Foundry is a comprehensive platform...

Starting self-reflection loop (max 3 iterations)...

Iteration 1/3:
----------------------------------------
Agent response: Azure AI Foundry offers many benefits including AI development tools, security features...
Groundedness score: 3/5
Requesting improvement...

Iteration 2/3:
----------------------------------------
Agent response: Based on the provided context, Azure AI Foundry provides seven key benefits...
Groundedness score: 5/5
✓ Score improved from 3 to 5!
✓ Perfect groundedness score achieved!

===============================================================================
RESULTS
===============================================================================

Best score achieved: 5/5
Best iteration: 2

Best response:
Based on the provided context, Azure AI Foundry provides seven key benefits...

✓ Perfect groundedness achieved! The agent's response is fully grounded in the context.
```

## Understanding the Evaluation

### Groundedness Score (1-5 scale)

The GroundednessEvaluator measures how well the agent's response is grounded in the provided context:

- **5** = Excellent - Response is fully grounded in context, no hallucinations
- **4** = Good - Mostly grounded with minor deviations
- **3** = Fair - Partially grounded but includes unsupported claims
- **2** = Poor - Significant amount of ungrounded content
- **1** = Very Poor - Response is largely unsupported by context

### Self-Reflection Process

1. **Initial Response**: Agent generates answer based on question
2. **Evaluation**: Groundedness evaluator scores the response (1-5)
3. **Feedback**: If score < 5, agent receives feedback explaining the score
4. **Reflection**: Agent analyzes its response and identifies improvements
5. **Retry**: Agent generates improved response
6. **Iteration**: Process repeats until perfect score or max iterations

### Key Benefits

- **Automatic Quality Improvement**: No manual intervention needed
- **Hallucination Reduction**: Ensures responses stay grounded in facts
- **Iterative Refinement**: Multiple attempts to achieve best quality
- **Measurable Progress**: Track improvement across iterations

## Customization Options

### Adjust Maximum Iterations

```csharp
const int MaxReflections = 5; // Increase for more improvement attempts
```

### Modify Evaluation Criteria

```csharp
// Use different evaluators from Microsoft.Extensions.AI.Evaluation.Quality:
var evaluator = new RelevanceEvaluator();  // Measures relevance
var evaluator = new CoherenceEvaluator();  // Measures coherence
var evaluator = new FluencyEvaluator();    // Measures fluency
```

### Use Multiple Evaluators

```csharp
var evaluators = new IEvaluator[]
{
    new GroundednessEvaluator(),
    new RelevanceEvaluator(),
    new CoherenceEvaluator()
};

// Evaluate with all evaluators and aggregate scores
```

### Change Reflection Prompt

```csharp
string reflectionPrompt = $"""
    Your response scored {score}/5 for groundedness.
    To improve:
    1. Cite specific information from the context
    2. Avoid adding information not in the context
    3. Structure your answer clearly
    Please provide an improved response.
    """;
```

## Best Practices

1. **Provide Complete Context**: Ensure grounding context contains all information needed to answer the question
2. **Clear Instructions**: Give the agent clear instructions about staying grounded in context
3. **Appropriate Iterations**: 3-5 iterations usually sufficient for most scenarios
4. **Use Quality Models**: GPT-4o or GPT-4o-mini recommended for evaluation
5. **Monitor Improvements**: Track scores across iterations to identify patterns
6. **Batch Processing**: For production, process multiple questions in batch

## Comparison with Python Sample

This .NET sample provides equivalent functionality to the Python `self_reflection.py`:

**Similarities:**
- Same self-reflection pattern and approach
- Same groundedness evaluation concept (1-5 scoring)
- Iterative improvement with feedback
- Tracking best response and iteration

**Differences:**
- .NET uses `Microsoft.Extensions.AI.Evaluation` package
- Python uses `azure-ai-projects` OpenAI Evals API
- .NET: Built-in evaluators (GroundednessEvaluator)
- Python: Custom evaluation using Azure AI Foundry service
- .NET sample uses single question; Python uses JSONL batch processing

## Troubleshooting

### Common Issues

1. **Low Initial Scores**
   - Issue: Agent consistently scores 1-2
   - Solution: Review context completeness and agent instructions
   - Tip: Ensure context contains all necessary information

2. **No Improvement Across Iterations**
   - Issue: Score doesn't improve after multiple iterations
   - Solution: Check reflection prompt clarity and model capability
   - Tip: Try using a more capable model (e.g., GPT-4o instead of GPT-4o-mini)

3. **Evaluation Errors**
   - Issue: Evaluator throws exceptions
   - Solution: Verify evaluator model deployment and endpoint
   - Tip: Ensure `AZURE_FOUNDRY_PROJECT_ENDPOINT` is correct

4. **Authentication Issues**
   - Error: Unauthorized
   - Solution: Run `az login` and verify project access
   - Reference: https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively

## Related Resources

- [Reflexion Paper (NeurIPS 2023)](https://arxiv.org/abs/2303.11366)
- [Microsoft.Extensions.AI.Evaluation Documentation](https://learn.microsoft.com/dotnet/ai/evaluation/libraries)
- [Azure AI Evaluation SDK](https://learn.microsoft.com/azure/ai-foundry/how-to/develop/evaluate-sdk)
- [GroundednessEvaluator API Reference](https://learn.microsoft.com/dotnet/api/microsoft.extensions.ai.evaluation.quality.groundednessevaluator)

## Advanced Scenarios

### Batch Processing

For processing multiple questions with self-reflection:

```csharp
var questions = new[] { question1, question2, question3 };
var results = new List<(string Question, double Score, string Response)>();

foreach (var question in questions)
{
    var (bestScore, bestResponse) = await RunSelfReflectionAsync(question, context);
    results.Add((question, bestScore, bestResponse));
}

// Analyze aggregate results
var avgScore = results.Average(r => r.Score);
Console.WriteLine($"Average groundedness score: {avgScore:F2}/5");
```

### Integration with CI/CD

Add self-reflection evaluation to your testing pipeline:

```csharp
[Fact]
public async Task Agent_Responses_Should_Be_Grounded()
{
    var (score, _) = await RunSelfReflectionAsync(testQuestion, testContext);
    Assert.True(score >= 4, $"Groundedness score {score} below threshold");
}
```

## Next Steps

After running self-reflection evaluation:
1. Implement similar patterns for other quality metrics (relevance, coherence, fluency)
2. Create batch processing for comprehensive evaluation datasets
3. Integrate into CI/CD pipeline for continuous quality assurance
4. Monitor production agent responses with automated evaluation
5. Explore the Red Teaming sample (Evaluation_Step01_RedTeaming) for safety assessment
