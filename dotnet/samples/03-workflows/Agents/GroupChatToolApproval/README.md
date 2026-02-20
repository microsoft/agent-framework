# Group Chat with Tool Approval Sample

This sample demonstrates how to use `GroupChatBuilder` with tools that require human approval before execution. A group of specialized agents collaborate on a task, and sensitive tool calls trigger human-in-the-loop approval.

## What This Sample Demonstrates

- Using a custom `GroupChatManager` with agents that have approval-required tools
- Handling `FunctionApprovalRequestContent` in group chat scenarios
- Multi-round group chat with tool approval interruption and resumption
- Integrating tool call approvals with multi-agent workflows where different agents have different levels of tool access

## How It Works

1. A `GroupChatBuilder` workflow is created with multiple specialized agents
2. A custom `DeploymentGroupChatManager` determines which agent speaks next based on conversation state
3. Agents collaborate on a software deployment task:
   - **QA Engineer**: Runs automated tests
   - **DevOps Engineer**: Checks staging status, creates rollback plan, and deploys to production
4. When the deployment agent tries to deploy to production, it triggers an approval request
5. The sample simulates human approval and the workflow completes

## Key Components

### Approval-Required Tools

The `DeployToProduction` function is wrapped with `ApprovalRequiredAIFunction` to require human approval:

```csharp
new ApprovalRequiredAIFunction(AIFunctionFactory.Create(DeployToProduction))
```

### Custom Group Chat Manager

The `DeploymentGroupChatManager` implements custom speaker selection logic:
- First iteration: QA Engineer runs tests
- Subsequent iterations: DevOps Engineer handles deployment tasks

### Approval Handling

The sample demonstrates continuous event-driven execution with inline approval handling:
- The workflow runs in a single event loop.
- When an approval-required tool is invoked, the loop surfaces an approval request, processes the (simulated) human response, and then continues execution without starting a separate phase.

## Prerequisites

- Azure OpenAI or OpenAI configured with the required environment variables
- `AZURE_OPENAI_ENDPOINT` environment variable set
- `AZURE_OPENAI_DEPLOYMENT_NAME` environment variable (defaults to "gpt-4o-mini")

## Running the Sample

```bash
dotnet run
```

## Expected Output

The sample will show:
1. QA Engineer running tests
2. DevOps Engineer checking staging and creating rollback plan
3. An approval request for production deployment
4. Simulated approval response
5. DevOps Engineer completing the deployment
6. Workflow completion message

## Related Samples

- [Agent Function Tools with Approvals](../../../02-agents/Agents/Agent_Step01_UsingFunctionToolsWithApprovals) - Basic function approval pattern
- [Agent Workflow Patterns](../../_StartHere/03_AgentWorkflowPatterns) - Group chat without approvals
- [Human-in-the-Loop Basic](../../HumanInTheLoop/HumanInTheLoopBasic) - Workflow-level human interaction
