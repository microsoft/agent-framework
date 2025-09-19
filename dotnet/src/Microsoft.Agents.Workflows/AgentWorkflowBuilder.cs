// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.ComponentModel;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;
#if NET
using System.Security.Cryptography;
#endif

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides utility methods for constructing common patterns of agent workflows.
/// </summary>
public static class AgentWorkflowBuilder
{
    /// <summary>
    /// Builds a <see cref="Workflow{T}"/> composed of a pipeline of agents where the output of one agent is the input to the next.
    /// </summary>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow<List<ChatMessage>> BuildSequential(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);

        // Create a builder that chains the agents together in sequence. The workflow simply begins
        // with the first agent in the sequence.
        WorkflowBuilder? builder = null;
        ExecutorIsh? previous = null;
        foreach (var agent in agents)
        {
            AIAgentHostExecutor agentExecutor = new(agent);

            if (builder is null)
            {
                builder = new WorkflowBuilder(agentExecutor);
            }
            else
            {
                Debug.Assert(previous is not null);
                builder.AddEdge(previous, agentExecutor);
            }

            previous = agentExecutor;
        }

        if (previous is null)
        {
            Throw.ArgumentException(nameof(agents), "At least one agent must be provided to build a sequential workflow.");
        }

        // Add an ending executor that batches up all messages from the last agent
        // so that it's published as a single list result.
        Debug.Assert(builder is not null);
        builder.AddEdge(previous, new SequentialEndExecutor());

        return builder.Build<List<ChatMessage>>();
    }

    /// <summary>
    /// Provides an executor that batches received chat messages that it then publishes as the final result
    /// when receiving a <see cref="TurnToken"/>.
    /// </summary>
    private sealed class SequentialEndExecutor : Executor
    {
        private readonly List<ChatMessage> _pendingMessages = [];

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder
                .AddHandler<ChatMessage>((message, context) => this._pendingMessages.Add(message))
                .AddHandler<List<ChatMessage>>((messages, _) => this._pendingMessages.AddRange(messages))
                .AddHandler<TurnToken>(async (token, context) =>
                {
                    var messages = new List<ChatMessage>(this._pendingMessages);
                    this._pendingMessages.Clear();
                    await context.AddEventAsync(new WorkflowCompletedEvent(messages)).ConfigureAwait(false);
                });
    }

    /// <summary>
    /// Builds a <see cref="Workflow{T}"/> composed of agents that operate concurrently on the same input,
    /// aggregating their outputs into a single collection.
    /// </summary>
    /// <param name="agents">The set of agents to compose into a concurrent workflow.</param>
    /// <param name="aggregator">
    /// The aggregation function that accepts a list of the output messages from each <paramref name="agents"/> and produces
    /// a single result list. If <see langword="null"/>, the default behavior is to return a list containing the last message
    /// from each agent that produced at least one message.
    /// </param>
    /// <returns>The built workflow composed of the supplied concurrent <paramref name="agents"/>.</returns>
    public static Workflow<List<ChatMessage>> BuildConcurrent(
        IEnumerable<AIAgent> agents,
        Func<IList<List<ChatMessage>>, List<ChatMessage>>? aggregator = null)
    {
        Throw.IfNull(agents);

        // A workflow needs a starting executor, so we create one that forwards everything to each agent.
        ForwardingExecutor start = new();
        WorkflowBuilder builder = new(start);

        // For each agent, we create an executor to host it and an accumulator to batch up its output messages,
        // so that the final accumulator receives a single list of messages from each agent. Otherwise, the
        // accumulator would not be able to determine what came from what agent, as there's currently no
        // provenance tracking exposed in the workflow context passed to a handler.
        ExecutorIsh[] agentExecutors = (from agent in agents select (ExecutorIsh)agent).ToArray();
        ExecutorIsh[] accumulators = [.. from agent in agentExecutors select (ExecutorIsh)new ChatMessageBatchingExecutor()];
        builder.AddFanOutEdge(start, targets: agentExecutors);
        for (int i = 0; i < agentExecutors.Length; i++)
        {
            builder.AddEdge(agentExecutors[i], accumulators[i]);
        }

        // Create the accumulating executor that will gather the results from each agent, and connect
        // each agent's accumulator to it. If no aggregation function was provided, we default to returning
        // the last message from each agent
        aggregator ??= static lists => (from list in lists where list.Count > 0 select list.Last()).ToList();
        ConcurrentEndExecutor end = new(agentExecutors.Length, aggregator);
        builder.AddFanInEdge(end, sources: accumulators);

        return builder.Build<List<ChatMessage>>();
    }

    /// <summary>Creates a new <see cref="HandoffsWorkflowBuilder"/> using <paramref name="initialAgent"/> as the starting agent in the workflow.</summary>
    /// <param name="initialAgent">The agent that will receive inputs provided to the workflow.</param>
    /// <returns>The builder for creating a workflow based on handoffs.</returns>
    /// <remarks>
    /// Handoffs between agents are achieved by the current agent invoking an <see cref="AITool"/> provided to an agent
    /// via <see cref="ChatClientAgentOptions"/>'s <see cref="ChatClientAgentOptions.ChatOptions"/>.<see cref="ChatOptions.Tools"/>.
    /// The <see cref="AIAgent"/> must be capable of understanding those <see cref="AgentRunOptions"/> provided. If the agent
    /// ignores the tools or is otherwise unable to advertize them to the underlying provider, handoffs will not occur.
    /// </remarks>
    public static HandoffsWorkflowBuilder StartHandoffWith(AIAgent initialAgent)
    {
        Throw.IfNull(initialAgent);
        return new(initialAgent);
    }

    /// <summary>Executor that forwards all relevant messages.</summary>
    private sealed class ForwardingExecutor : Executor
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<object>((message, context) => context.SendMessageAsync(message));
    }

    /// <summary>
    /// Provides an executor that batches received chat messages that it then releases when
    /// receiving a <see cref="TurnToken"/>.
    /// </summary>
    private sealed class ChatMessageBatchingExecutor : Executor
    {
        private readonly List<ChatMessage> _pendingMessages = [];

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder
                .AddHandler<ChatMessage>((message, context) => this._pendingMessages.Add(message))
                .AddHandler<List<ChatMessage>>((messages, _) => this._pendingMessages.AddRange(messages))
                .AddHandler<TurnToken>(async (token, context) =>
                {
                    var messages = new List<ChatMessage>(this._pendingMessages);
                    this._pendingMessages.Clear();

                    await context.SendMessageAsync(messages).ConfigureAwait(false);
                    await context.SendMessageAsync(token).ConfigureAwait(false);
                });
    }

    /// <summary>
    /// Provides an executor that accepts the output messages from each of the concurrent agents
    /// and produces a result list containing the last message from each.
    /// </summary>
    private sealed class ConcurrentEndExecutor : Executor
    {
        private readonly int _expectedInputs;
        private readonly Func<IList<List<ChatMessage>>, List<ChatMessage>> _aggregator;
        private List<List<ChatMessage>> _allResults;
        private int _remaining;

        public ConcurrentEndExecutor(int expectedInputs, Func<IList<List<ChatMessage>>, List<ChatMessage>> aggregator)
        {
            this._expectedInputs = expectedInputs;
            this._aggregator = Throw.IfNull(aggregator);

            this._allResults = new List<List<ChatMessage>>(expectedInputs);
            this._remaining = expectedInputs;
        }

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<List<ChatMessage>>(async (messages, context) =>
            {
                this._allResults.Add(messages);
                if (--this._remaining == 0)
                {
                    this._remaining = this._expectedInputs;
                    var results = this._allResults;
                    this._allResults = new List<List<ChatMessage>>(this._expectedInputs);
                    await context.AddEventAsync(new WorkflowCompletedEvent(this._aggregator(results))).ConfigureAwait(false);
                }
            });
    }

    /// <summary>
    /// Defines the orchestration handoff relationships for all agents in the system.
    /// </summary>
    public sealed class HandoffsWorkflowBuilder
    {
        private const string FunctionPrefix = "handoff_to_";
        private readonly AIAgent _initialAgent;
        private readonly Dictionary<AIAgent, HashSet<HandoffTarget>> _targets = [];
        private readonly Dictionary<string, AIAgent> _allAgents = [];

        /// <summary>
        /// Initializes a new instance of the <see cref="HandoffsWorkflowBuilder"/> class with no handoff relationships.
        /// </summary>
        /// <param name="initialAgent">The first agent to be invoked (prior to any handoff).</param>
        internal HandoffsWorkflowBuilder(AIAgent initialAgent)
        {
            this._initialAgent = initialAgent;
            this._allAgents.Add(initialAgent.Id, initialAgent);
        }

        /// <summary>
        /// Gets or sets additional instructions to provide to an agent about how to perform handoffs.
        /// </summary>
        /// <remarks>
        /// By default, simple instructions are included. This may be set to <see langword="null"/> to avoid including
        /// any additional instructions, or may be customized to provide more specific guidance.
        /// </remarks>
        public string? HandoffInstructions { get; set; } =
             $"""
              You are part of a multi-agent system. Each agent encompasses instructions and tools and can hand off a conversation to another agent
              when appropriate. Handoffs are achieved by calling a handoff function, generally named `{FunctionPrefix}<agent_id>`. Handoffs
              between agents are handled seamlessly in the background; do not mention or draw attention to these handoffs in your conversation with the user.
              """;

        /// <summary>
        /// Adds handoff relationships from a source agent to one or more target agents.
        /// </summary>
        /// <param name="from">The source agent.</param>
        /// <param name="to">The target agents to add as handoff targets for the source agent.</param>
        /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
        /// <remarks>The handoff reason for each target is derived from its description or name.</remarks>
        public HandoffsWorkflowBuilder WithHandoff(AIAgent from, IEnumerable<AIAgent> to)
        {
            Throw.IfNull(from);
            Throw.IfNull(to);

            foreach (var target in to)
            {
                if (target is null)
                {
                    Throw.ArgumentNullException(nameof(to), "One or more target agents are null.");
                }

                this.WithHandoff(from, target);
            }

            return this;
        }

        /// <summary>
        /// Adds a handoff relationship from a source agent to a target agent with a custom handoff reason.
        /// </summary>
        /// <param name="from">The source agent.</param>
        /// <param name="to">The target agent.</param>
        /// <param name="handoffReason">The reason the <paramref name="from"/> should hand off to the <paramref name="to"/>.</param>
        /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
        public HandoffsWorkflowBuilder WithHandoff(AIAgent from, AIAgent to, string? handoffReason = null)
        {
            Throw.IfNull(from);
            Throw.IfNull(to);

#if NET
            this._allAgents.TryAdd(from.Id, from);
            this._allAgents.TryAdd(to.Id, to);
#else
            if (!this._allAgents.ContainsKey(from.Id))
            {
                this._allAgents.Add(from.Id, from);
            }

            if (!this._allAgents.ContainsKey(to.Id))
            {
                this._allAgents.Add(to.Id, to);
            }
#endif

            if (!this._targets.TryGetValue(from, out var handoffs))
            {
                this._targets[from] = handoffs = [];
            }

            if (string.IsNullOrWhiteSpace(handoffReason))
            {
                handoffReason = to.Description ?? to.Name ?? (to as ChatClientAgent)?.Instructions;
                if (string.IsNullOrWhiteSpace(handoffReason))
                {
                    Throw.ArgumentException(
                        nameof(to),
                        $"The provided target agent '{to.DisplayName}' has no description, name, or instructions, and no handoff description has been provided. " +
                        "At least one of these is required to register a handoff so that the appropriate target agent can be chosen.");
                }
            }

            if (!handoffs.Add(new(to, handoffReason)))
            {
                Throw.InvalidOperationException($"A handoff from agent '{from.DisplayName}' to agent '{to.DisplayName}' has already been registered.");
            }

            return this;
        }

        /// <summary>
        /// Builds a <see cref="Workflow{T}"/> composed of agents that operate via handoffs, with the next
        /// agent to process messages selected by the current agent.
        /// </summary>
        /// <returns>The workflow built based on the handoffs in the builder.</returns>
        public Workflow<List<ChatMessage>> Build()
        {
            StartHandoffs start = new();
            EndExecutor end = new();
            WorkflowBuilder builder = new(start);

            // Create an AgentExecutor for each again.
            Dictionary<string, AgentExecutor> executors = this._allAgents.ToDictionary(a => a.Key, a => new AgentExecutor(a.Value, this.HandoffInstructions));

            // Connect the start executor to the initial agent.
            builder.AddEdge(start, executors[this._initialAgent.Id]);

            // Initialize each executor with its handoff targets to the other executors.
            foreach (var agent in this._allAgents)
            {
                executors[agent.Key].Initialize(builder, end, executors,
                    this._targets.TryGetValue(agent.Value, out HashSet<HandoffTarget>? targets) ? targets : []);
            }

            // Build the workflow.
            return builder.Build<List<ChatMessage>>();
        }

        /// <summary>Describes a handoff to a specific target <see cref="AIAgent"/>.</summary>
        private readonly record struct HandoffTarget(AIAgent Target, string? Reason = null)
        {
            public bool Equals(HandoffTarget other) => this.Target.Id == other.Target.Id;
            public override int GetHashCode() => this.Target.Id.GetHashCode();
        }

        /// <summary>Executor used at the start of a handoffs workflow to accumulate messages and emit them as HandoffState upon receiving a turn token.</summary>
        private sealed class StartHandoffs : Executor
        {
            private readonly List<ChatMessage> _pendingMessages = [];

            protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
                routeBuilder
                    .AddHandler<string>((message, context) => this._pendingMessages.Add(new(ChatRole.User, message)))
                    .AddHandler<ChatMessage>((message, context) => this._pendingMessages.Add(message))
                    .AddHandler<IEnumerable<ChatMessage>>((messages, _) => this._pendingMessages.AddRange(messages))
                    .AddHandler<ChatMessage[]>((messages, _) => this._pendingMessages.AddRange(messages)) // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
                    .AddHandler<List<ChatMessage>>((messages, _) => this._pendingMessages.AddRange(messages))  // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
                    .AddHandler<TurnToken>(async (token, context) =>
                    {
                        var messages = new List<ChatMessage>(this._pendingMessages);
                        this._pendingMessages.Clear();
                        await context.SendMessageAsync(new HandoffState(token, null, messages)).ConfigureAwait(false);
                    });
        }

        /// <summary>Executor used at the end of a handoff workflow to raise a final completed event.</summary>
        private sealed class EndExecutor : Executor
        {
            protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
                routeBuilder.AddHandler<HandoffState>((handoff, context) =>
                    context.AddEventAsync(new WorkflowCompletedEvent(handoff.Messages)));
        }

        /// <summary>Executor used to represent an agent in a handoffs workflow, responding to <see cref="HandoffState"/> events.</summary>
        private sealed class AgentExecutor(
            AIAgent agent,
            string? instructions) : Executor($"{agent.DisplayName}/{CreateId()}")
        {
            private static readonly JsonElement s_handoffSchema = AIFunctionFactory.Create(
                ([Description("The reason for the handoff")] string? reasonForHandoff) => { }).JsonSchema;
            private static readonly AIFunctionDeclaration s_endFunction = AIFunctionFactory.CreateDeclaration(
                name: $"end_{CreateId()}",
                description: "Invoke this function when all work is completed and no further interactions are required.",
                jsonSchema: AIFunctionFactory.Create(() => { }).JsonSchema);

            private readonly AIAgent _agent = agent;
            private readonly HashSet<string> _handoffFunctionNames = [];
            private readonly ChatClientAgentRunOptions _agentOptions = new()
            {
                ChatOptions = new()
                {
                    Instructions = instructions,
                    Tools = [s_endFunction],
                }
            };

            public void Initialize(
                WorkflowBuilder builder,
                Executor end,
                Dictionary<string, AgentExecutor> executors,
                IEnumerable<HandoffTarget> handoffs) =>
                builder.AddSwitch(this, sb =>
                {
                    foreach (HandoffTarget handoff in handoffs)
                    {
                        var handoffFunc = AIFunctionFactory.CreateDeclaration($"{FunctionPrefix}{CreateId()}", handoff.Reason, s_handoffSchema);

                        this._handoffFunctionNames.Add(handoffFunc.Name);

                        this._agentOptions.ChatOptions!.Tools!.Add(handoffFunc);
                        this._agentOptions.ChatOptions.AllowMultipleToolCalls = false;

                        sb.AddCase<HandoffState>(state => state?.InvokedHandoff == handoffFunc.Name, executors[handoff.Target.Id]);
                    }

                    sb.WithDefault(end);
                });

            protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
                routeBuilder.AddHandler<HandoffState>(async (handoffState, context) =>
                    {
                        string? requestedHandoff = null;
                        List<AgentRunResponseUpdate> updates = [];
                        List<ChatMessage> allMessages = handoffState.Messages;

                        while (requestedHandoff is null)
                        {
                            updates.Clear();
                            await foreach (var update in this._agent.RunStreamingAsync(allMessages, options: this._agentOptions).ConfigureAwait(false))
                            {
                                await AddUpdateAsync(update).ConfigureAwait(false);
                                for (int i = 0; i < update.Contents.Count; i++)
                                {
                                    var c = update.Contents[i];
                                    if (c is FunctionCallContent fcc)
                                    {
                                        if (this._handoffFunctionNames.Contains(fcc.Name))
                                        {
                                            requestedHandoff = fcc.Name;
                                            await AddUpdateAsync(new AgentRunResponseUpdate
                                            {
                                                AgentId = this._agent.Id,
                                                AuthorName = this._agent.DisplayName,
                                                Contents = [new FunctionResultContent(fcc.CallId, "Transferred.")],
                                                CreatedAt = DateTimeOffset.UtcNow,
                                                MessageId = Guid.NewGuid().ToString("N"),
                                                Role = ChatRole.Tool,
                                            }).ConfigureAwait(false);
                                        }
                                        else if (fcc.Name == s_endFunction.Name)
                                        {
                                            requestedHandoff = s_endFunction.Name;
                                            update.Contents.RemoveAt(i);
                                            i--;
                                        }
                                    }
                                }
                            }

                            allMessages.AddRange(updates.ToAgentRunResponse().Messages);
                        }

                        await context.SendMessageAsync(new HandoffState(handoffState.TurnToken, requestedHandoff, allMessages)).ConfigureAwait(false);

                        async Task AddUpdateAsync(AgentRunResponseUpdate update)
                        {
                            updates.Add(update);
                            if (handoffState.TurnToken.EmitEvents is true)
                            {
                                await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update)).ConfigureAwait(false);
                            }
                        }
                    });
        }

        private record class HandoffState(
            TurnToken TurnToken,
            string? InvokedHandoff,
            List<ChatMessage> Messages);

        private static string CreateId() =>
#if NET
            RandomNumberGenerator.GetString("abcdefghijklmnopqrstuvwxyz0123456789", 24);
#else
            Guid.NewGuid().ToString("N");
#endif
    }
}
