// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.UnitTests;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step6EntryPoint
{
    public const string EchoAgentId = "echo";
    public const string EchoPrefix = "You said: ";

    public static Workflow CreateWorkflow(int maxTurns) =>
        AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = maxTurns })
            .AddParticipants(new HelloAgent(), new TestEchoAgent(id: EchoAgentId, prefix: EchoPrefix))
            .Build();

    public static async ValueTask RunAsync(TextWriter writer, IWorkflowExecutionEnvironment environment, int maxSteps = 2)
    {
        Workflow workflow = CreateWorkflow(maxSteps);

        StreamingRun run = await environment.StreamAsync(workflow, Array.Empty<ChatMessage>())
                                    .ConfigureAwait(false);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompletedEvent executorCompleted)
            {
                Debug.WriteLine($"{executorCompleted.ExecutorId}: {executorCompleted.Data}");
            }
            else if (evt is AgentRunUpdateEvent update)
            {
                AgentRunResponse response = update.AsResponse();

                foreach (ChatMessage message in response.Messages)
                {
                    writer.WriteLine($"{update.ExecutorId}: {message.Text}");
                }
            }
        }
    }
}

internal sealed class HelloAgent(string id = nameof(HelloAgent)) : AIAgent
{
    public const string Greeting = "Hello World!";
    public const string DefaultId = nameof(HelloAgent);

    public override string Id => id;
    public override string? Name => id;

    public override AgentThread GetNewThread()
        => new HelloAgentThread();

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new HelloAgentThread();

    public override async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        IEnumerable<AgentRunResponseUpdate> update = [
            await this.RunStreamingAsync(messages, thread, options, cancellationToken)
                      .SingleAsync(cancellationToken)
                      .ConfigureAwait(false)];

        return update.ToAgentRunResponse();
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        yield return new(ChatRole.Assistant, "Hello World!")
        {
            AgentId = this.Id,
            AuthorName = this.Name,
            MessageId = Guid.NewGuid().ToString("N"),
        };
    }
}

internal sealed class HelloAgentThread() : InMemoryAgentThread();
