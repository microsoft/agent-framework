# Marketing Copy Workflow

This sample demonstrates a sequential multi-agent pipeline for generating marketing copy from a product description.

## Overview

The workflow showcases:
- **Sequential Agent Pipeline**: Three agents work in sequence, each building on the previous output
- **Role-Based Agents**: Each agent has a distinct responsibility
- **Content Transformation**: Raw product info transforms into polished marketing copy

## Agent Pipeline

```
Product Description
       |
       v
  AnalystAgent  --> Key features, audience, USPs
       |
       v
   WriterAgent  --> Draft marketing copy
       |
       v
   EditorAgent  --> Polished final copy
       |
       v
  Final Output
```

## Agents

| Agent | Role |
|-------|------|
| AnalystAgent | Identifies key features, target audience, and unique selling points |
| WriterAgent | Creates compelling marketing copy (~150 words) |
| EditorAgent | Polishes grammar, clarity, tone, and formatting |

## Usage

```bash
# Run the demonstration with mock responses
python main.py
```

## Example Input

```
An eco-friendly stainless steel water bottle that keeps drinks cold for 24 hours.
```

## Configuration

For production use, configure these agents in Azure AI Foundry:

### AnalystAgent
```
Instructions: You are a marketing analyst. Given a product description, identify:
- Key features
- Target audience
- Unique selling points
```

### WriterAgent
```
Instructions: You are a marketing copywriter. Given a block of text describing
features, audience, and USPs, compose a compelling marketing copy (like a
newsletter section) that highlights these points. Output should be short
(around 150 words), output just the copy as a single text block.
```

### EditorAgent
```
Instructions: You are an editor. Given the draft copy, correct grammar,
improve clarity, ensure consistent tone, give format and make it polished.
Output the final improved copy as a single text block.
```
