// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using AGUI.Client;
using AGUI.WorkflowNested;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

public sealed class NestedWorkflowTests
{
    [Fact]
    public async Task ClientRejectsDuplicateActiveLocalExecutorIdsFromParallelSubworkflowsAsync()
    {
        // Arrange
        Workflow workflow = NestedWorkflow.Create();
        await using WorkflowTestHost host = await WorkflowTestHost.StartAsync(
            workflow.AsAIAgent(name: "NestedWorkflow", includeWorkflowOutputsInResponse: true));
        AGUIChatClient chatClient = new(new(host.Client, ""));
        AIAgent clientAgent = chatClient.AsAIAgent(name: "client");
        AgentSession session = await clientAgent.CreateSessionAsync();

        // Act
        Func<Task> act = async () => _ = await clientAgent
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"), session)
            .ToListAsync();

        // Assert
        await act.Should().ThrowAsync<InvalidOperationException>()
            .WithMessage("*Step \"Analyze_Analyze\" is already active*");
    }
}
