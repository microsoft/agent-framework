// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use GroupChatBuilder with tools that require human
// approval before execution. A group of specialized agents collaborate on a task, and
// sensitive tool calls trigger human-in-the-loop approval.
//
// This sample works as follows:
// 1. A GroupChatBuilder workflow is created with multiple specialized agents.
// 2. A custom manager determines which agent speaks next based on conversation state.
// 3. Agents collaborate on a software deployment task.
// 4. When the deployment agent tries to deploy to production, it triggers an approval request.
// 5. The sample simulates human approval and the workflow completes.
//
// Purpose:
// Show how tool call approvals integrate with multi-agent group chat workflows where
// different agents have different levels of tool access.
//
// Demonstrate:
// - Using custom GroupChatManager with agents that have approval-required tools.
// - Handling FunctionApprovalRequestContent in group chat scenarios.
// - Multi-round group chat with tool approval interruption and resumption.

using System.ComponentModel;
using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowGroupChatToolApprovalSample;

/// <summary>
/// This sample demonstrates how to use GroupChatBuilder with tools that require human
/// approval before execution.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - An Azure OpenAI chat completion deployment must be configured.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        // 1. Create AI client
        IChatClient client = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
            .GetChatClient(deploymentName)
            .AsIChatClient();

        // 2. Create specialized agents with their tools
        ChatClientAgent qaEngineer = new(
            client,
            "You are a QA engineer responsible for running tests before deployment. Run the appropriate test suites and report results clearly.",
            "QAEngineer",
            "QA engineer who runs tests",
            [AIFunctionFactory.Create(RunTests)]);

        ChatClientAgent devopsEngineer = new(
            client,
            "You are a DevOps engineer responsible for deployments. First check staging status and create a rollback plan, then proceed with production deployment. Always ensure safety measures are in place before deploying.",
            "DevOpsEngineer",
            "DevOps engineer who handles deployments",
            [
                AIFunctionFactory.Create(CheckStagingStatus),
                AIFunctionFactory.Create(CreateRollbackPlan),
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(DeployToProduction))
            ]);

        // 3. Create custom GroupChatManager with speaker selection logic
        DeploymentGroupChatManager manager = new([qaEngineer, devopsEngineer])
        {
            MaximumIterationCount = 4  // Limit to 4 rounds
        };

        // 4. Build a group chat workflow with the custom manager
        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(_ => manager)
            .AddParticipants(qaEngineer, devopsEngineer)
            .Build();

        // 5. Start the workflow
        Console.WriteLine("Starting group chat workflow for software deployment...");
        Console.WriteLine($"Agents: [{qaEngineer.Name}, {devopsEngineer.Name}]");
        Console.WriteLine(new string('-', 60));

        List<ChatMessage> messages = [new(ChatRole.User, "We need to deploy version 2.4.0 to production. Please coordinate the deployment.")];

        await using StreamingRun run = await InProcessExecution.Lockstep.RunStreamingAsync(workflow, messages);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        string? lastExecutorId = null;
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            switch (evt)
            {
                case RequestInfoEvent e:
                {
                    if (e.Request.TryGetDataAs(out FunctionApprovalRequestContent? approvalRequestContent))
                    {
                        Console.WriteLine();
                        Console.WriteLine($"[APPROVAL REQUIRED] From agent: {e.Request.PortInfo.PortId}");
                        Console.WriteLine($"  Tool: {approvalRequestContent.FunctionCall.Name}");
                        Console.WriteLine($"  Arguments: {JsonSerializer.Serialize(approvalRequestContent.FunctionCall.Arguments)}");
                        Console.WriteLine();

                        // Approve the tool call request
                        Console.WriteLine($"Tool: {approvalRequestContent.FunctionCall.Name} approved");
                        await run.SendResponseAsync(e.Request.CreateResponse(approvalRequestContent.CreateResponse(approved: true)));
                    }

                    break;
                }

                case AgentResponseUpdateEvent e:
                {
                    if (e.ExecutorId != lastExecutorId)
                    {
                        if (lastExecutorId is not null)
                        {
                            Console.WriteLine();
                        }

                        Console.WriteLine($"- {e.ExecutorId}: ");
                        lastExecutorId = e.ExecutorId;
                    }

                    Console.Write(e.Update.Text);

                    break;
                }
            }
        }

        Console.WriteLine();
        Console.WriteLine(new string('-', 60));
        Console.WriteLine("Deployment workflow completed successfully!");
        Console.WriteLine("All agents have finished their tasks.");
    }

    // Tool definitions - These are called by the agents during workflow execution
    [Description("Run automated tests for the application.")]
    private static string RunTests([Description("Name of the test suite to run")] string testSuite)
        => $"Test suite '{testSuite}' completed: 47 passed, 0 failed, 0 skipped";

    [Description("Check the current status of the staging environment.")]
    private static string CheckStagingStatus()
        => "Staging environment: Healthy, Version 2.3.0 deployed, All services running";

    [Description("Deploy specified components to production. Requires human approval.")]
    private static string DeployToProduction(
        [Description("The version to deploy")] string version,
        [Description("Comma-separated list of components to deploy")] string components)
        => $"Production deployment complete: Version {version}, Components: {components}";

    [Description("Create a rollback plan for the deployment.")]
    private static string CreateRollbackPlan([Description("The version being deployed")] string version)
        => $"Rollback plan created for version {version}: Automated rollback to v2.2.0 if health checks fail within 5 minutes";
}
