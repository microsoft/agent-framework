// Copyright (c) Microsoft. All rights reserved.

using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class WorkflowHostAgentTests
{
    [Fact]
    public void GetService_Workflow_ReturnsHostedWorkflow()
    {
        // Arrange
        var french = new TestEchoAgent("french", "french");
        var spanish = new TestEchoAgent("spanish", "spanish");
        var workflow = new WorkflowBuilder(french).AddEdge(french, spanish).Build();

        // Act
        var host = workflow.AsAIAgent(name: "host");

        // Assert: the host exposes the inner workflow so callers can inspect its executor ids.
        host.GetService<Workflow>().Should().BeSameAs(workflow);
    }

    [Fact]
    public void GetService_Workflow_OnPlainAgent_ReturnsNull()
    {
        // Arrange
        var agent = new TestEchoAgent("solo", "solo");

        // Act + Assert: a non-workflow agent does not resolve a Workflow service.
        agent.GetService<Workflow>().Should().BeNull();
    }
}
