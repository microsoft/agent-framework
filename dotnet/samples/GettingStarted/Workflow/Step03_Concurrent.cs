// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Workflow;

/// <summary>
/// This class demonstrates a simple concurrent workflow with the "fan-out" and "fan-in" patterns.
/// This workflow consists of 4 executors, two of which are agents. The other two are the StartExecutor
/// and the AggregationExecutor. The StartExecutor initiates the workflow by sending the same input
/// message to both agents concurrently (fan-out). Each agent then processes the message independently
/// and in parallel, returning their responses to the AggregationExecutor (fan-in). The AggregationExecutor
/// collects the responses and produces the final output.
/// </summary>
public class Step03_Concurrent(ITestOutputHelper output) : WorkflowSample(output)
{
    [Fact]
    public async Task RunAsync()
    {
        // Create the executors
        ChatClientAgent physicist = new(
            GetAzureOpenAIChatClient(),
            name: "Physicist",
            instructions: "You are an expert in physics. You answer questions from a physics perspective."
        );
        ChatClientAgent chemist = new(
            GetAzureOpenAIChatClient(),
            name: "Chemist",
            instructions: "You are an expert in chemistry. You answer questions from a chemistry perspective."
        );
        var startExecutor = new ConcurrentStartExecutor();
        var aggregationExecutor = new ConcurrentAggregationExecutor();

        // Build the workflow
        WorkflowBuilder builder = new(startExecutor);
        builder.AddFanOutEdge(startExecutor, targets: [physicist, chemist]);
        builder.AddFanInEdge(aggregationExecutor, sources: [physicist, chemist]);
        var workflow = builder.Build<string>();

        // Execute the workflow in streaming mode
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, "What is temperature?");
        //await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is WorkflowCompletedEvent completed)
            {
                Console.WriteLine($"Workflow completed with results:\n{completed.Data}");
            }
        }
    }

    private sealed class ConcurrentStartExecutor() :
        ReflectingExecutor<ConcurrentStartExecutor>("ConcurrentStartExecutor"),
        IMessageHandler<string>
    {
        public async ValueTask HandleAsync(string message, IWorkflowContext context)
        {
            await context.SendMessageAsync(new ChatMessage(ChatRole.User, message));
            await context.SendMessageAsync(new TurnToken(emitEvents: true));
        }
    }

    private sealed class ConcurrentAggregationExecutor() :
        ReflectingExecutor<ConcurrentAggregationExecutor>("ConcurrentAggregationExecutor"),
        IMessageHandler<ChatMessage>
    {
        private readonly List<ChatMessage> _messages = [];

        public async ValueTask HandleAsync(ChatMessage message, IWorkflowContext context)
        {
            _messages.Add(message);

            if (_messages.Count == 2)
            {
                var formattedMessages = string.Join(Environment.NewLine, _messages.Select(m => $"{m.AuthorName}: {m.Text}"));
                await context.AddEventAsync(new WorkflowCompletedEvent(formattedMessages));
            }
        }
    }
}
