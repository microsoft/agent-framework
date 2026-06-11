# Self-Reflection Evaluation Sample

This sample demonstrates the self-reflection pattern using Agent Framework and Azure AI Foundry's Groundedness Evaluator. For details, see [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366) (NeurIPS 2023).

## Overview

**What it demonstrates:**
- Iterative self-reflection loop that automatically improves responses based on groundedness evaluation
- Using `FoundryEvals` to score each iteration via the Foundry Groundedness evaluator
- Batch processing of prompts from JSONL files with progress tracking
- Using `FoundryChatClient` with a Project Endpoint and Azure CLI authentication
- Comprehensive summary statistics and detailed result tracking

## Prerequisites

### Azure Resources
- **Azure AI Foundry project**: Deploy models (default: gpt-5.2 for both agent and judge)
- **Azure CLI**: Run `az login` to authenticate

### Environment Variables
```bash
FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
```

## Running the Sample

```bash
# Basic usage
uv run python samples/05-end-to-end/evaluation/self_reflection/self_reflection.py

# With options
python self_reflection.py --input my_prompts.jsonl \
                          --output results.jsonl \
                          --max-reflections 5 \
                          -n 10
```

**CLI Options:**
- `--input`, `-i`: Input JSONL file
- `--output`, `-o`: Output JSONL file
- `--agent-model`, `-m`: Agent model name (default: gpt-5.2)
- `--judge-model`, `-e`: Evaluator model name (default: gpt-5.2)
- `--max-reflections`: Max iterations (default: 3)
- `--limit`, `-n`: Process only first N prompts

## Understanding Results

The agent iteratively improves responses:
1. Generate initial response
2. Evaluate groundedness via `FoundryEvals` (1-5 scale)
3. If score < 5, provide feedback and retry
4. Stop at max iterations or perfect score (5/5)

**Example output:**
```
[1/31] Processing prompt 0...
  Self-reflection iteration 1/3...
  Groundedness score: 3/5
  Self-reflection iteration 2/3...
  Groundedness score: 5/5
  ✓ Perfect groundedness score achieved!
  ✓ Completed with score: 5/5 (best at iteration 2/3)
```

In the Foundry UI, under `Build`/`Evaluations` you can view detailed results for each prompt, including:
- Context
- Query
- Response
- Groundedness scores and reasoning for each iteration of each prompt

## Related Resources

- [Reflexion Paper](https://arxiv.org/abs/2303.11366)
- [Azure AI Evaluation SDK](https://learn.microsoft.com/azure/ai-studio/how-to/develop/evaluate-sdk)
- [Agent Framework](https://github.com/microsoft/agent-framework)
