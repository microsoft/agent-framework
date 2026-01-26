# Workflow Loop Sample

This sample demonstrates how to run a cyclic workflow (containing loops) as a durable orchestration.

## Overview

The workflow iteratively improves a slogan based on AI feedback until it meets quality criteria.

### Executors

- **SloganWriter** - Generates slogans using AI (handles string and FeedbackResult)
- **FeedbackProvider** - Evaluates slogans (calls YieldOutput to accept, SendMessage to loop)

## Key Concepts

- Cyclic Workflow Support (back-edges)
- Multi-Type Executor Handlers
- Message Routing via SendMessageAsync
- Workflow Termination via YieldOutputAsync

## Running

Set AZURE_OPENAI_ENDPOINT and run: dotnet run
