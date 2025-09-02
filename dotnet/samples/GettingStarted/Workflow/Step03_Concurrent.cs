// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Workflow;

/// <summary>
/// This sample demonstrates concurrent execution using "fan-out" and "fan-in" patterns.
///
/// Unlike sequential workflows where executors run one after another, this workflow
/// runs multiple executors in parallel to process the same input simultaneously.
///
/// The workflow structure:
/// 1. StartExecutor sends the same question to two AI agents concurrently (fan-out)
/// 2. Physicist Agent and Chemist Agent answer independently and in parallel
/// 3. AggregationExecutor collects both responses and combines them (fan-in)
///
/// This pattern is useful when you want multiple perspectives on the same input,
/// or when you can break work into independent parallel tasks for better performance.
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
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is WorkflowCompletedEvent completed)
            {
                Console.WriteLine($"Workflow completed with results:\n{completed.Data}");
            }
        }
    }

    /// <summary>
    /// Executor that starts the concurrent processing by sending messages to the agents.
    /// </summary>
    private sealed class ConcurrentStartExecutor() :
        ReflectingExecutor<ConcurrentStartExecutor>("ConcurrentStartExecutor"),
        IMessageHandler<string>
    {
        /// <summary>
        /// Starts the concurrent processing by sending messages to the agents.
        /// </summary>
        /// <param name="message">The user message to process</param>
        /// <param name="context">Workflow context for accessing workflow services and adding events</param>
        /// <returns></returns>
        public async ValueTask HandleAsync(string message, IWorkflowContext context)
        {
            // Broadcast the message to all connected agents. Receiving agents will queue
            // the message but will not start processing until they receive a turn token.
            await context.SendMessageAsync(new ChatMessage(ChatRole.User, message));
            // Broadcast the turn token to kick off the agents.
            await context.SendMessageAsync(new TurnToken(emitEvents: true));
        }
    }

    /// <summary>
    /// Executor that aggregates the results from the concurrent agents.
    /// </summary>
    private sealed class ConcurrentAggregationExecutor() :
        ReflectingExecutor<ConcurrentAggregationExecutor>("ConcurrentAggregationExecutor"),
        IMessageHandler<ChatMessage>
    {
        private readonly List<ChatMessage> _messages = [];

        /// <summary>
        /// Handles incoming messages from the agents and aggregates their responses.
        /// </summary>
        /// <param name="message">The message from the agent</param>
        /// <param name="context">Workflow context for accessing workflow services and adding events</param>
        /// <returns></returns>
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
