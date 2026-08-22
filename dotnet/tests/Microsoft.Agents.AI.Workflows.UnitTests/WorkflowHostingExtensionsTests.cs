// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Covers <see cref="WorkflowHostingExtensions.WithCheckpointing"/>, which lets a host redirect
/// where an already-built workflow agent writes its checkpoints.
/// </summary>
public class WorkflowHostingExtensionsTests
{
    [Fact]
    public void WithCheckpointing_AgentThatDoesNotHostAWorkflow_IsLeftAlone()
    {
        // Arrange
        AIAgent agent = new OrchestrationTestHelpers.DoubleEchoAgent("plain");

        // Act
        AIAgent result = agent.WithCheckpointing(CheckpointManager.CreateInMemory());

        // Assert
        Assert.Same(agent, result);
    }

    [Fact]
    public void WithCheckpointing_WorkflowAgentWithoutAnExplicitStore_IsRedirected()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);

        // Act
        AIAgent result = agent.WithCheckpointing(CheckpointManager.CreateInMemory());

        // Assert: a copy is produced, and the original object is not modified.
        Assert.NotSame(agent, result);
        Assert.Equal(agent.Id, result.Id);
        Assert.Equal(agent.Name, result.Name);
        Assert.Equal(agent.Description, result.Description);
    }

    [Fact]
    public void WithCheckpointing_AppliedTwice_StopsAfterTheFirstRedirection()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);
        AIAgent redirected = agent.WithCheckpointing(CheckpointManager.CreateInMemory());

        // Act
        AIAgent again = redirected.WithCheckpointing(CheckpointManager.CreateInMemory());

        // Assert: the copy already names a checkpoint manager, so it is now the explicit choice.
        Assert.Same(redirected, again);
    }

    [Fact]
    public void WithCheckpointing_CallerAlreadyChoseAStore_DoesNotOverrideIt()
    {
        // Arrange
        InProcessExecutionEnvironment callerChoice = InProcessExecution.Lockstep.WithCheckpointing(CheckpointManager.CreateInMemory());
        AIAgent agent = BuildWorkflowAgent(callerChoice);

        // Act
        AIAgent result = agent.WithCheckpointing(CheckpointManager.CreateInMemory());

        // Assert
        Assert.Same(agent, result);
    }

    [Fact]
    public void WithCheckpointing_WorkflowAgentBehindAWrapper_IsLeftAlone()
    {
        // Arrange: only the innermost agent could be copied, and returning it alone would throw the
        // wrapper away, so a wrapped workflow agent is deliberately not redirected.
        AIAgent wrapper = new PassThroughAgent(BuildWorkflowAgent(executionEnvironment: null));

        // Act
        AIAgent result = wrapper.WithCheckpointing(CheckpointManager.CreateInMemory());

        // Assert
        Assert.Same(wrapper, result);
    }

    [Fact]
    public void WithCheckpointing_NullArguments_Throw()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ((AIAgent)null!).WithCheckpointing(CheckpointManager.CreateInMemory()));
        Assert.Throws<ArgumentNullException>(() => agent.WithCheckpointing(null!));
    }

    [Fact]
    public void GetService_WorkflowAgent_ExposesItsMetadata()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);

        // Act
        var metadata = agent.GetService<WorkflowAgentMetadata>();

        // Assert: getting an instance back is what identifies a workflow agent.
        Assert.NotNull(metadata);
        Assert.False(metadata.UsesOwnCheckpointStorage);
    }

    [Fact]
    public void GetService_WorkflowAgent_DoesNotAnswerTheBaseAgentMetadataType()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);

        // Act & Assert: AIAgentMetadata names the inference service behind an agent, which a
        // workflow does not have, so the agent leaves that question unanswered as it did before.
        Assert.Null(agent.GetService<AIAgentMetadata>());
    }

    [Fact]
    public void GetService_WorkflowAgentWithItsOwnStore_SaysSo()
    {
        // Arrange
        InProcessExecutionEnvironment callerChoice = InProcessExecution.Lockstep.WithCheckpointing(CheckpointManager.CreateInMemory());
        AIAgent agent = BuildWorkflowAgent(callerChoice);

        // Act
        var metadata = agent.GetService<WorkflowAgentMetadata>();

        // Assert
        Assert.NotNull(metadata);
        Assert.True(metadata.UsesOwnCheckpointStorage);
    }

    [Fact]
    public async Task GetService_WorkflowSession_ExposesCheckpointRecoveryAsync()
    {
        // Arrange
        AIAgent agent = BuildWorkflowAgent(
            InProcessExecution.Lockstep.WithCheckpointing(CheckpointManager.CreateInMemory()));
        AgentSession session = await agent.CreateSessionAsync();
        WorkflowSessionCheckpointRecovery recovery = session.GetService<WorkflowSessionCheckpointRecovery>()
            ?? throw new InvalidOperationException("Workflow checkpoint recovery was not available.");

        // Act
        bool prepared = recovery.TryPrepare("checkpoint-from-response");

        // Assert
        Assert.True(prepared);
        CheckpointInfo? checkpoint = recovery.CurrentCheckpoint;
        Assert.NotNull(checkpoint);
        Assert.Equal("checkpoint-from-response", checkpoint.CheckpointId);
        Assert.False(string.IsNullOrWhiteSpace(checkpoint.SessionId));
    }

    [Fact]
    public void GetService_NonWorkflowSession_HasNoCheckpointRecovery()
    {
        // Arrange
        var session = new NonWorkflowSession();

        // Act
        WorkflowSessionCheckpointRecovery? recovery =
            session.GetService<WorkflowSessionCheckpointRecovery>();

        // Assert
        Assert.Null(recovery);
    }

    [Fact]
    public void GetService_WorkflowAgentBehindAWrapper_IsStillFound()
    {
        // Arrange: detection has to see through middleware, which is why it goes through GetService
        // rather than testing the type of the agent.
        AIAgent wrapper = new PassThroughAgent(BuildWorkflowAgent(executionEnvironment: null));

        // Act
        var metadata = wrapper.GetService<WorkflowAgentMetadata>();

        // Assert
        Assert.NotNull(metadata);
    }

    [Fact]
    public void GetService_AgentThatDoesNotHostAWorkflow_HasNoWorkflowMetadata()
    {
        // Arrange
        AIAgent agent = new OrchestrationTestHelpers.DoubleEchoAgent("plain");

        // Act & Assert
        Assert.Null(agent.GetService<WorkflowAgentMetadata>());
    }

    [Fact]
    public void GetService_WithAServiceKey_ReturnsNothing()
    {
        // Arrange: a key means something this agent knows nothing about, so it must not answer.
        AIAgent agent = BuildWorkflowAgent(executionEnvironment: null);

        // Act & Assert
        Assert.Null(agent.GetService(typeof(WorkflowAgentMetadata), serviceKey: "some-key"));
    }

    private static AIAgent BuildWorkflowAgent(InProcessExecutionEnvironment? executionEnvironment)
    {
        OrchestrationTestHelpers.DoubleEchoAgent inner = new("inner");
        Workflow workflow = new ConcurrentWorkflowBuilder(inner).WithOutputFrom(inner).Build();

        return workflow.AsAIAgent(
            id: "workflow-agent",
            name: "WorkflowAgent",
            description: "A workflow hosted as an agent.",
            executionEnvironment: executionEnvironment);
    }

    private sealed class PassThroughAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent);

    private sealed class NonWorkflowSession : AgentSession;
}
