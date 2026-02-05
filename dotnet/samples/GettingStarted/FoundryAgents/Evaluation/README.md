# Foundry Agents - Evaluation Samples

This directory contains samples demonstrating how to evaluate Agent Framework agents for safety, quality, and performance using Azure AI Foundry's evaluation capabilities.

## Overview

Evaluation is critical for building trustworthy and high-quality AI applications. These samples show how to:

- **Assess Safety**: Use red teaming to identify vulnerabilities and ensure agents handle adversarial inputs safely
- **Measure Quality**: Evaluate response quality with groundedness, relevance, coherence, and other metrics
- **Improve Iteratively**: Implement self-reflection patterns where agents automatically improve their responses

## Samples

### Evaluation_Step01_RedTeaming

Demonstrates Azure AI's RedTeam functionality to assess agent safety and resilience against adversarial attacks.

**Key Features:**
- Multiple attack strategies (ROT13, Binary, Leetspeak, Character manipulation, etc.)
- Multiple risk categories (Violence, HateUnfairness, Sexual, SelfHarm)
- Async callback pattern for agent integration
- Attack success rate (ASR) metrics

**Use Cases:**
- Pre-deployment safety testing
- Identifying prompt injection vulnerabilities
- Testing agent guardrails and safety instructions
- Continuous security assessment

[View Red Teaming Sample](./Evaluation_Step01_RedTeaming/README.md)

### Evaluation_Step02_SelfReflection

Demonstrates the self-reflection pattern where agents iteratively improve responses based on groundedness evaluation.

**Key Features:**
- Groundedness evaluation (1-5 scoring)
- Iterative improvement loop
- Context-grounded response generation
- Quality tracking across iterations

**Use Cases:**
- Reducing hallucinations
- Ensuring factual accuracy
- RAG (Retrieval-Augmented Generation) quality assurance
- Automated response quality improvement

[View Self Reflection Sample](./Evaluation_Step02_SelfReflection/README.md)

## Prerequisites

All evaluation samples require:

- **.NET 10 SDK or later**
- **Azure AI Foundry project** (hub and project)
- **Azure OpenAI deployment** (gpt-4o or gpt-4o-mini recommended)
- **Azure CLI** authentication (`az login`)

### Creating Azure Resources

1. **Create Azure AI Hub and Project**:
   ```bash
   # Follow the Azure Portal wizard or use Azure CLI
   az ml workspace create --kind hub --name my-ai-hub --resource-group my-rg
   az ml workspace create --kind project --name my-ai-project --resource-group my-rg
   ```
   Reference: https://learn.microsoft.com/azure/ai-foundry/how-to/create-projects

2. **Deploy Azure OpenAI Model**:
   - Navigate to Azure OpenAI resource in Azure Portal
   - Deploy gpt-4o or gpt-4o-mini model
   - Note the deployment name and endpoint

3. **Set Environment Variables**:
   ```powershell
   $env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-project.api.azureml.ms"
   $env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"
   ```

## NuGet Packages Used

The evaluation samples use the following packages:

- **Azure.AI.Projects** - Core Azure AI Foundry client for agents and evaluations
- **Azure.Identity** - Azure authentication (AzureCliCredential)
- **Microsoft.Extensions.AI.Evaluation** - Base evaluation interfaces and utilities
- **Microsoft.Extensions.AI.Evaluation.Quality** - Quality evaluators (Groundedness, Relevance, Coherence, etc.)
- **Microsoft.Extensions.AI.Evaluation.Safety** - Safety evaluators (Content safety, Protected material, etc.)
- **Microsoft.Agents.AI.AzureAI** - Agent Framework Azure AI integration

## Evaluation Workflow

### 1. Development Phase
- Use self-reflection to ensure quality responses
- Test with various inputs and contexts
- Iterate on agent instructions and guardrails

### 2. Pre-Deployment Phase
- Run comprehensive red team evaluations
- Test against known vulnerabilities
- Validate safety instructions and content filtering
- Aim for Attack Success Rate (ASR) < 5%

### 3. Production Phase
- Implement continuous evaluation in CI/CD pipeline
- Monitor agent responses in production
- Periodic red teaming to catch new vulnerabilities
- Track quality metrics over time

## Evaluation Metrics

### Safety Metrics

| Metric | Description | Tool | Target |
|--------|-------------|------|--------|
| Attack Success Rate (ASR) | Percentage of successful adversarial attacks | Red Teaming | < 5% |
| Content Safety | Detects harmful content (hate, violence, etc.) | Safety Evaluators | Low risk |
| Jailbreak Resistance | Resistance to instruction bypass attempts | Red Teaming | High |

### Quality Metrics

| Metric | Description | Tool | Range |
|--------|-------------|------|-------|
| Groundedness | Response grounded in provided context | GroundednessEvaluator | 1-5 |
| Relevance | Response relevance to the question | RelevanceEvaluator | 1-5 |
| Coherence | Logical flow and clarity | CoherenceEvaluator | 1-5 |
| Fluency | Language quality and naturalness | FluencyEvaluator | 1-5 |
| Completeness | Response completeness | CompletenessEvaluator | 1-5 |

## Best Practices

### Safety Evaluation

1. **Test Multiple Attack Vectors**: Use diverse attack strategies (encoding, obfuscation, social engineering)
2. **Cover All Risk Categories**: Test Violence, HateUnfairness, Sexual, SelfHarm, and domain-specific risks
3. **Iterate on Findings**: Review successful attacks and strengthen guardrails
4. **Regular Testing**: Re-test after any agent changes
5. **Document Results**: Track ASR over time to measure improvement

### Quality Evaluation

1. **Comprehensive Context**: Provide complete grounding context for best results
2. **Multiple Evaluators**: Use combination of evaluators (groundedness + relevance + coherence)
3. **Appropriate Models**: Use GPT-4o or GPT-4o-mini for evaluation tasks
4. **Batch Processing**: Evaluate multiple scenarios for representative results
5. **Threshold Setting**: Define acceptable quality scores for your use case

### Continuous Improvement

1. **Automated Pipeline**: Integrate evaluation into CI/CD
2. **Regression Testing**: Ensure changes don't reduce quality or safety
3. **Monitoring**: Track metrics in production
4. **Feedback Loop**: Use evaluation results to improve agent design
5. **Version Comparison**: Compare evaluations across agent versions

## Related Documentation

### Azure AI Foundry
- [Azure AI Foundry Overview](https://learn.microsoft.com/azure/ai-foundry/)
- [Create Projects and Resources](https://learn.microsoft.com/azure/ai-foundry/how-to/create-projects)
- [Evaluation SDK](https://learn.microsoft.com/azure/ai-foundry/how-to/develop/evaluate-sdk)

### Evaluation and Safety
- [Risk and Safety Evaluations](https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-metrics-built-in#risk-and-safety-evaluators)
- [Azure AI Red Teaming](https://learn.microsoft.com/azure/ai-foundry/how-to/develop/run-scans-ai-red-teaming-agent)
- [Microsoft.Extensions.AI.Evaluation](https://learn.microsoft.com/dotnet/ai/evaluation/libraries)

### Agent Framework
- [Agent Framework Documentation](https://github.com/microsoft/agent-framework)
- [Foundry Agents Samples](../README.md)
- [Observability Sample](../FoundryAgents_Step07_Observability/README.md)

## Academic References

- **Reflexion**: Shinn et al. (NeurIPS 2023) - [Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)
- **PyRIT**: Microsoft - [Python Risk Identification Toolkit](https://github.com/Azure/PyRIT)
- **OWASP LLM Top 10**: [Security risks for LLM applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- **MITRE ATLAS**: [Adversarial threat landscape for AI systems](https://atlas.mitre.org/)

## Troubleshooting

### Common Issues

**Authentication Errors**
```
Error: Unauthorized or credential issues
Solution: Run 'az login' and ensure access to Azure AI project
```

**Missing Resources**
```
Error: Project or deployment not found
Solution: Verify AZURE_FOUNDRY_PROJECT_ENDPOINT and deployment name
```

**Regional Availability**
```
Error: Feature not available in region
Solution: Some evaluation features require specific Azure regions
Check: https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-metrics-built-in
```

**Package Compatibility**
```
Error: Package version conflicts
Solution: Ensure all packages are compatible versions
Use: dotnet list package to check versions
```

## Sample Comparison: .NET vs Python

| Feature | .NET | Python |
|---------|------|--------|
| Red Teaming | Azure.AI.Projects.RedTeam | azure-ai-evaluation.RedTeam |
| Groundedness Eval | Microsoft.Extensions.AI.Evaluation.Quality | azure-ai-projects Evals API |
| Auth Pattern | AzureCliCredential | AzureCliCredential |
| Async Support | async/await | asyncio |
| Agent Integration | Microsoft.Agents.AI | agent_framework |
| Batch Processing | Manual implementation | Built-in (JSONL) |

Both implementations provide equivalent functionality with language-specific optimizations.

## Next Steps

1. **Start with Self-Reflection**: Learn quality evaluation basics
2. **Add Red Teaming**: Assess safety before deployment
3. **Integrate into Pipeline**: Automate evaluation in CI/CD
4. **Monitor Production**: Track metrics in live applications
5. **Explore Advanced**: Custom evaluators, composite evaluations, reporting

## Contributing

For issues or suggestions related to evaluation samples, please file an issue in the [agent-framework repository](https://github.com/microsoft/agent-framework/issues).

## License

These samples are licensed under the MIT License. See [LICENSE](../../../../../LICENSE) for details.
