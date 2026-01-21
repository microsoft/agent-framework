// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class ExpectedException : Exception
{
    public ExpectedException(string message)
        : base(message)
    {
    }

    public ExpectedException() : base()
    {
    }

    public ExpectedException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}

public class WorkflowHostSmokeTests
{
    private sealed class AlwaysFailsAIAgent(bool failByThrowing) : AIAgent
    {
        private sealed class Thread : InMemoryAgentThread
        {
            public Thread() { }

            public Thread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
                : base(serializedThread, jsonSerializerOptions)
            { }
        }

        public override ValueTask<AgentThread> DeserializeThreadAsync(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            return new(new Thread(serializedThread, jsonSerializerOptions));
        }

        public override ValueTask<AgentThread> GetNewThreadAsync(CancellationToken cancellationToken = default)
        {
            return new(new Thread());
        }

        protected override async Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            return await this.RunStreamingAsync(messages, thread, options, cancellationToken)
                             .ToAgentResponseAsync(cancellationToken);
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            const string ErrorMessage = "Simulated agent failure.";
            if (failByThrowing)
            {
                throw new ExpectedException(ErrorMessage);
            }

            yield return new AgentResponseUpdate(ChatRole.Assistant, [new ErrorContent(ErrorMessage)]);
        }
    }

    private static Workflow CreateWorkflow(bool failByThrowing)
    {
        ExecutorBinding agent = new AlwaysFailsAIAgent(failByThrowing).BindAsExecutor(emitEvents: true);

        return new WorkflowBuilder(agent).Build();
    }

    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task Test_AsAgent_ErrorContentStreamedOutAsync(bool includeExceptionDetails, bool failByThrowing)
    {
        string expectedMessage = !failByThrowing || includeExceptionDetails
                               ? "Simulated agent failure."
                               : "An error occurred while executing the workflow.";

        // Arrange is done by the caller.
        Workflow workflow = CreateWorkflow(failByThrowing);

        // Act
        List<AgentResponseUpdate> updates = await workflow.AsAgent("WorkflowAgent", includeExceptionDetails: includeExceptionDetails)
                                                             .RunStreamingAsync(new ChatMessage(ChatRole.User, "Hello"))
                                                             .ToListAsync();

        // Assert
        bool hadErrorContent = false;
        foreach (AgentResponseUpdate update in updates)
        {
            if (update.Contents.Any())
            {
                // We should expect a single update which contains the error content.
                update.Contents.Should().ContainSingle()
                                        .Which.Should().BeOfType<ErrorContent>()
                                        .Which.Message.Should().Be(expectedMessage);
                hadErrorContent = true;
            }
        }

        hadErrorContent.Should().BeTrue();
    }
}
