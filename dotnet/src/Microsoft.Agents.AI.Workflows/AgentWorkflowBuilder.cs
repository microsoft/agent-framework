// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides utility methods for constructing common patterns of workflows composed of agents.
/// </summary>
public static partial class AgentWorkflowBuilder
{
    /// <summary>
    /// Builds a <see cref="Workflow{T}"/> composed of a pipeline of agents where the output of one agent is the input to the next.
    /// </summary>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow BuildSequential(params IEnumerable<AIAgent> agents)
        => BuildSequentialCore(workflowName: null, agents);

    /// <summary>
    /// Builds a <see cref="Workflow{T}"/> composed of a pipeline of agents where the output of one agent is the input to the next.
    /// </summary>
    /// <param name="workflowName">The name of workflow.</param>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow BuildSequential(string workflowName, params IEnumerable<AIAgent> agents)
        => BuildSequentialCore(workflowName, agents);

    private static Workflow BuildSequentialCore(string? workflowName, params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);

        // Create a builder that chains the agents together in sequence. The workflow simply begins
        // with the first agent in the sequence.
        WorkflowBuilder? builder = null;
        ExecutorIsh? previous = null;
        foreach (var agent in agents)
        {
            AgentRunStreamingExecutor agentExecutor = new(agent, includeInputInOutput: true);

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

        OutputMessagesExecutor end = new();
        builder = builder.AddEdge(previous, end).WithOutputFrom(end);
        if (workflowName is not null)
        {
            builder = builder.WithName(workflowName);
        }
        return builder.Build();
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
    public static Workflow BuildConcurrent(
        IEnumerable<AIAgent> agents,
        Func<IList<List<ChatMessage>>, List<ChatMessage>>? aggregator = null)
        => BuildConcurrentCore(workflowName: null, agents, aggregator);

    /// <summary>
    /// Builds a <see cref="Workflow{T}"/> composed of agents that operate concurrently on the same input,
    /// aggregating their outputs into a single collection.
    /// </summary>
    /// <param name="workflowName">The name of the workflow.</param>
    /// <param name="agents">The set of agents to compose into a concurrent workflow.</param>
    /// <param name="aggregator">
    /// The aggregation function that accepts a list of the output messages from each <paramref name="agents"/> and produces
    /// a single result list. If <see langword="null"/>, the default behavior is to return a list containing the last message
    /// from each agent that produced at least one message.
    /// </param>
    /// <returns>The built workflow composed of the supplied concurrent <paramref name="agents"/>.</returns>
    public static Workflow BuildConcurrent(
        string workflowName,
        IEnumerable<AIAgent> agents,
        Func<IList<List<ChatMessage>>, List<ChatMessage>>? aggregator = null)
        => BuildConcurrentCore(workflowName, agents, aggregator);

    private static Workflow BuildConcurrentCore(
        string? workflowName,
        IEnumerable<AIAgent> agents,
        Func<IList<List<ChatMessage>>, List<ChatMessage>>? aggregator = null)
    {
        Throw.IfNull(agents);

        // A workflow needs a starting executor, so we create one that forwards everything to each agent.
        ChatForwardingExecutor start = new("Start");
        WorkflowBuilder builder = new(start);

        // For each agent, we create an executor to host it and an accumulator to batch up its output messages,
        // so that the final accumulator receives a single list of messages from each agent. Otherwise, the
        // accumulator would not be able to determine what came from what agent, as there's currently no
        // provenance tracking exposed in the workflow context passed to a handler.
        ExecutorIsh[] agentExecutors = (from agent in agents select (ExecutorIsh)new AgentRunStreamingExecutor(agent, includeInputInOutput: false)).ToArray();
        ExecutorIsh[] accumulators = [.. from agent in agentExecutors select (ExecutorIsh)new BatchChatMessagesToListExecutor($"Batcher/{agent.Id}")];
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

        builder = builder.WithOutputFrom(end);
        if (workflowName is not null)
        {
            builder = builder.WithName(workflowName);
        }
        return builder.Build();
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
    public static HandoffsWorkflowBuilder CreateHandoffBuilderWith(AIAgent initialAgent)
    {
        Throw.IfNull(initialAgent);
        return new(initialAgent);
    }

    /// <summary>Creates a new <see cref="GroupChatWorkflowBuilder"/> with <paramref name="managerFactory"/>.</summary>
    /// <param name="managerFactory">
    /// Function that will create the <see cref="GroupChatManager"/> for the workflow instance. The manager will be
    /// provided with the set of agents that will participate in the group chat.
    /// </param>
    /// <returns>The builder for creating a workflow based on handoffs.</returns>
    /// <remarks>
    /// Handoffs between agents are achieved by the current agent invoking an <see cref="AITool"/> provided to an agent
    /// via <see cref="ChatClientAgentOptions"/>'s <see cref="ChatClientAgentOptions.ChatOptions"/>.<see cref="ChatOptions.Tools"/>.
    /// The <see cref="AIAgent"/> must be capable of understanding those <see cref="AgentRunOptions"/> provided. If the agent
    /// ignores the tools or is otherwise unable to advertize them to the underlying provider, handoffs will not occur.
    /// </remarks>
    public static GroupChatWorkflowBuilder CreateGroupChatBuilderWith(Func<IReadOnlyList<AIAgent>, GroupChatManager> managerFactory)
    {
        Throw.IfNull(managerFactory);
        return new GroupChatWorkflowBuilder(managerFactory);
    }

    /// <summary>
    /// Executor that runs the agent and forwards all messages, input and output, to the next executor.
    /// </summary>
    private sealed class AgentRunStreamingExecutor(AIAgent agent, bool includeInputInOutput) : Executor(GetDescriptiveIdFromAgent(agent)), IResettableExecutor
    {
        private readonly List<ChatMessage> _pendingMessages = [];

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder
                .AddHandler<string>((message, _, __) => this._pendingMessages.Add(new(ChatRole.User, message)))
                .AddHandler<ChatMessage>((message, _, __) => this._pendingMessages.Add(message))
                .AddHandler<IEnumerable<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))
                .AddHandler<ChatMessage[]>((messages, _, __) => this._pendingMessages.AddRange(messages)) // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
                .AddHandler<List<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))  // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
                .AddHandler<TurnToken>(async (token, context, cancellationToken) =>
                {
                    List<ChatMessage> messages = [.. this._pendingMessages];
                    this._pendingMessages.Clear();

                    List<ChatMessage>? roleChanged = ChangeAssistantToUserForOtherParticipants(agent.DisplayName, messages);

                    List<AgentRunResponseUpdate> updates = [];
                    await foreach (var update in agent.RunStreamingAsync(messages, cancellationToken: cancellationToken).ConfigureAwait(false))
                    {
                        updates.Add(update);
                        if (token.EmitEvents is true)
                        {
                            await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
                        }
                    }

                    ResetUserToAssistantForChangedRoles(roleChanged);

                    if (!includeInputInOutput)
                    {
                        messages.Clear();
                    }

                    messages.AddRange(updates.ToAgentRunResponse().Messages);

                    await context.SendMessageAsync(messages, cancellationToken: cancellationToken).ConfigureAwait(false);
                    await context.SendMessageAsync(token, cancellationToken: cancellationToken).ConfigureAwait(false);
                });

        public ValueTask ResetAsync()
        {
            this._pendingMessages.Clear();
            return default;
        }
    }

    /// <summary>
    /// Provides an executor that batches received chat messages that it then publishes as the final result
    /// when receiving a <see cref="TurnToken"/>.
    /// </summary>
    private sealed class OutputMessagesExecutor() : ChatProtocolExecutor("OutputMessages"), IResettableExecutor
    {
        protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
            => context.YieldOutputAsync(messages, cancellationToken);

        ValueTask IResettableExecutor.ResetAsync() => this.ResetAsync();
    }

    /// <summary>Executor that forwards all messages.</summary>
    private sealed class ChatForwardingExecutor(string id) : Executor(id), IResettableExecutor
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder
                    .AddHandler<string>((message, context, cancellationToken) => context.SendMessageAsync(new ChatMessage(ChatRole.User, message), cancellationToken: cancellationToken))
                    .AddHandler<ChatMessage>((message, context, cancellationToken) => context.SendMessageAsync(message, cancellationToken: cancellationToken))
                    .AddHandler<List<ChatMessage>>((messages, context, cancellationToken) => context.SendMessageAsync(messages, cancellationToken: cancellationToken))
                    .AddHandler<TurnToken>((turnToken, context, cancellationToken) => context.SendMessageAsync(turnToken, cancellationToken: cancellationToken));

        public ValueTask ResetAsync() => default;
    }

    /// <summary>
    /// Provides an executor that batches received chat messages that it then releases when
    /// receiving a <see cref="TurnToken"/>.
    /// </summary>
    private sealed class BatchChatMessagesToListExecutor(string id) : ChatProtocolExecutor(id), IResettableExecutor
    {
        protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
            => context.SendMessageAsync(messages, cancellationToken: cancellationToken);

        ValueTask IResettableExecutor.ResetAsync() => this.ResetAsync();
    }

    /// <summary>
    /// Provides an executor that accepts the output messages from each of the concurrent agents
    /// and produces a result list containing the last message from each.
    /// </summary>
    private sealed class ConcurrentEndExecutor : Executor, IResettableExecutor
    {
        private readonly int _expectedInputs;
        private readonly Func<IList<List<ChatMessage>>, List<ChatMessage>> _aggregator;
        private List<List<ChatMessage>> _allResults;
        private int _remaining;

        public ConcurrentEndExecutor(int expectedInputs, Func<IList<List<ChatMessage>>, List<ChatMessage>> aggregator) : base("ConcurrentEnd")
        {
            this._expectedInputs = expectedInputs;
            this._aggregator = Throw.IfNull(aggregator);

            this._allResults = new List<List<ChatMessage>>(expectedInputs);
            this._remaining = expectedInputs;
        }

        private void Reset()
        {
            this._allResults = new List<List<ChatMessage>>(this._expectedInputs);
            this._remaining = this._expectedInputs;
        }

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<List<ChatMessage>>(async (messages, context, cancellationToken) =>
            {
                // TODO: https://github.com/microsoft/agent-framework/issues/784
                // This locking should not be necessary.
                bool done;
                lock (this._allResults)
                {
                    this._allResults.Add(messages);
                    done = --this._remaining == 0;
                }

                if (done)
                {
                    this._remaining = this._expectedInputs;

                    var results = this._allResults;
                    this._allResults = new List<List<ChatMessage>>(this._expectedInputs);
                    await context.YieldOutputAsync(this._aggregator(results), cancellationToken).ConfigureAwait(false);
                }
            });

        public ValueTask ResetAsync()
        {
            this.Reset();
            return default;
        }
    }

    /// <summary>
    /// Provides a builder for specifying the handoff relationships between agents and building the resulting workflow.
    /// </summary>
    public sealed class HandoffsWorkflowBuilder
    {
        private const string FunctionPrefix = "handoff_to_";
        private readonly AIAgent _initialAgent;
        private readonly Dictionary<AIAgent, HashSet<HandoffTarget>> _targets = [];
        private readonly HashSet<AIAgent> _allAgents = new(AIAgentIDEqualityComparer.Instance);

        /// <summary>
        /// Initializes a new instance of the <see cref="HandoffsWorkflowBuilder"/> class with no handoff relationships.
        /// </summary>
        /// <param name="initialAgent">The first agent to be invoked (prior to any handoff).</param>
        internal HandoffsWorkflowBuilder(AIAgent initialAgent)
        {
            this._initialAgent = initialAgent;
            this._allAgents.Add(initialAgent);
        }

        /// <summary>
        /// Gets or sets additional instructions to provide to an agent that has handoffs about how and when to perform them.
        /// </summary>
        /// <remarks>
        /// By default, simple instructions are included. This may be set to <see langword="null"/> to avoid including
        /// any additional instructions, or may be customized to provide more specific guidance.
        /// </remarks>
        public string? HandoffInstructions { get; set; } =
             $"""
              You are one agent in a multi-agent system. You can hand off the conversation to another agent if appropriate. Handoffs are achieved
              by calling a handoff function, named in the form `{FunctionPrefix}<agent_id>`; the description of the function provides details on the
              target agent of that handoff. Handoffs between agents are handled seamlessly in the background; never mention or narrate these handoffs
              in your conversation with the user.
              """;

        /// <summary>
        /// Adds handoff relationships from a source agent to one or more target agents.
        /// </summary>
        /// <param name="from">The source agent.</param>
        /// <param name="to">The target agents to add as handoff targets for the source agent.</param>
        /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
        /// <remarks>The handoff reason for each target in <paramref name="to"/> is derived from that agent's description or name.</remarks>
        public HandoffsWorkflowBuilder WithHandoffs(AIAgent from, IEnumerable<AIAgent> to)
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
        /// Adds handoff relationships from one or more sources agent to a target agent.
        /// </summary>
        /// <param name="from">The source agents.</param>
        /// <param name="to">The target agent to add as a handoff target for each source agent.</param>
        /// <param name="handoffReason">
        /// The reason the <paramref name="from"/> should hand off to the <paramref name="to"/>.
        /// If <see langword="null"/>, the reason is derived from <paramref name="to"/>'s description or name.
        /// </param>
        /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
        public HandoffsWorkflowBuilder WithHandoffs(IEnumerable<AIAgent> from, AIAgent to, string? handoffReason = null)
        {
            Throw.IfNull(from);
            Throw.IfNull(to);

            foreach (var source in from)
            {
                if (source is null)
                {
                    Throw.ArgumentNullException(nameof(from), "One or more source agents are null.");
                }

                this.WithHandoff(source, to, handoffReason);
            }

            return this;
        }

        /// <summary>
        /// Adds a handoff relationship from a source agent to a target agent with a custom handoff reason.
        /// </summary>
        /// <param name="from">The source agent.</param>
        /// <param name="to">The target agent.</param>
        /// <param name="handoffReason">
        /// The reason the <paramref name="from"/> should hand off to the <paramref name="to"/>.
        /// If <see langword="null"/>, the reason is derived from <paramref name="to"/>'s description or name.
        /// </param>
        /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
        public HandoffsWorkflowBuilder WithHandoff(AIAgent from, AIAgent to, string? handoffReason = null)
        {
            Throw.IfNull(from);
            Throw.IfNull(to);

            this._allAgents.Add(from);
            this._allAgents.Add(to);

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
        public Workflow Build()
        {
            StartHandoffsExecutor start = new();
            EndHandoffsExecutor end = new();
            WorkflowBuilder builder = new(start);

            // Create an AgentExecutor for each again.
            Dictionary<string, HandoffAgentExecutor> executors = this._allAgents.ToDictionary(a => a.Id, a => new HandoffAgentExecutor(a, this.HandoffInstructions));

            // Connect the start executor to the initial agent.
            builder.AddEdge(start, executors[this._initialAgent.Id]);

            // Initialize each executor with its handoff targets to the other executors.
            foreach (var agent in this._allAgents)
            {
                executors[agent.Id].Initialize(builder, end, executors,
                    this._targets.TryGetValue(agent, out HashSet<HandoffTarget>? targets) ? targets : []);
            }

            // Build the workflow.
            return builder.WithOutputFrom(end).Build();
        }

        /// <summary>Describes a handoff to a specific target <see cref="AIAgent"/>.</summary>
        private readonly record struct HandoffTarget(AIAgent Target, string? Reason = null)
        {
            public bool Equals(HandoffTarget other) => this.Target.Id == other.Target.Id;
            public override int GetHashCode() => this.Target.Id.GetHashCode();
        }

        /// <summary>Executor used at the start of a handoffs workflow to accumulate messages and emit them as HandoffState upon receiving a turn token.</summary>
        private sealed class StartHandoffsExecutor() : Executor("HandoffStart"), IResettableExecutor
        {
            private readonly List<ChatMessage> _pendingMessages = [];

            protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
                routeBuilder
                    .AddHandler<string>((message, context, _) => this._pendingMessages.Add(new(ChatRole.User, message)))
                    .AddHandler<ChatMessage>((message, context, _) => this._pendingMessages.Add(message))
                    .AddHandler<IEnumerable<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))
                    .AddHandler<ChatMessage[]>((messages, _, __) => this._pendingMessages.AddRange(messages)) // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
                    .AddHandler<List<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))  // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
                    .AddHandler<TurnToken>(async (token, context, cancellationToken) =>
                    {
                        var messages = new List<ChatMessage>(this._pendingMessages);
                        this._pendingMessages.Clear();
                        await context.SendMessageAsync(new HandoffState(token, null, messages), cancellationToken: cancellationToken)
                                     .ConfigureAwait(false);
                    });

            public ValueTask ResetAsync()
            {
                this._pendingMessages.Clear();
                return default;
            }
        }

        /// <summary>Executor used at the end of a handoff workflow to raise a final completed event.</summary>
        private sealed class EndHandoffsExecutor() : Executor("HandoffEnd"), IResettableExecutor
        {
            protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
                routeBuilder.AddHandler<HandoffState>((handoff, context, cancellationToken) =>
                    context.YieldOutputAsync(handoff.Messages, cancellationToken));

            public ValueTask ResetAsync() => default;
        }

        /// <summary>Executor used to represent an agent in a handoffs workflow, responding to <see cref="HandoffState"/> events.</summary>
        private sealed class HandoffAgentExecutor(
            AIAgent agent,
            string? handoffInstructions) : Executor(GetDescriptiveIdFromAgent(agent)), IResettableExecutor
        {
            private static readonly JsonElement s_handoffSchema = AIFunctionFactory.Create(
                ([Description("The reason for the handoff")] string? reasonForHandoff) => { }).JsonSchema;

            private readonly AIAgent _agent = agent;
            private readonly HashSet<string> _handoffFunctionNames = [];
            private ChatClientAgentRunOptions? _agentOptions;

            public void Initialize(
                WorkflowBuilder builder,
                Executor end,
                Dictionary<string, HandoffAgentExecutor> executors,
                HashSet<HandoffTarget> handoffs) =>
                builder.AddSwitch(this, sb =>
                {
                    if (handoffs.Count != 0)
                    {
                        Debug.Assert(this._agentOptions is null);
                        this._agentOptions = new()
                        {
                            ChatOptions = new()
                            {
                                AllowMultipleToolCalls = false,
                                Instructions = handoffInstructions,
                                Tools = [],
                            },
                        };

                        foreach (HandoffTarget handoff in handoffs)
                        {
                            var handoffFunc = AIFunctionFactory.CreateDeclaration($"{FunctionPrefix}{GetDescriptiveIdFromAgent(handoff.Target)}", handoff.Reason, s_handoffSchema);

                            this._handoffFunctionNames.Add(handoffFunc.Name);

                            this._agentOptions.ChatOptions.Tools.Add(handoffFunc);

                            sb.AddCase<HandoffState>(state => state?.InvokedHandoff == handoffFunc.Name, executors[handoff.Target.Id]);
                        }
                    }

                    sb.WithDefault(end);
                });

            protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
                routeBuilder.AddHandler<HandoffState>(async (handoffState, context, cancellationToken) =>
                {
                    string? requestedHandoff = null;
                    List<AgentRunResponseUpdate> updates = [];
                    List<ChatMessage> allMessages = handoffState.Messages;

                    List<ChatMessage>? roleChanges = ChangeAssistantToUserForOtherParticipants(this._agent.DisplayName, allMessages);

                    await foreach (var update in this._agent.RunStreamingAsync(allMessages,
                                                                               options: this._agentOptions,
                                                                               cancellationToken: cancellationToken)
                                                            .ConfigureAwait(false))
                    {
                        await AddUpdateAsync(update, cancellationToken).ConfigureAwait(false);

                        foreach (var c in update.Contents)
                        {
                            if (c is FunctionCallContent fcc && this._handoffFunctionNames.Contains(fcc.Name))
                            {
                                requestedHandoff = fcc.Name;
                                await AddUpdateAsync(
                                    new AgentRunResponseUpdate
                                    {
                                        AgentId = this._agent.Id,
                                        AuthorName = this._agent.DisplayName,
                                        Contents = [new FunctionResultContent(fcc.CallId, "Transferred.")],
                                        CreatedAt = DateTimeOffset.UtcNow,
                                        MessageId = Guid.NewGuid().ToString("N"),
                                        Role = ChatRole.Tool,
                                    },
                                    cancellationToken
                                 )
                                .ConfigureAwait(false);
                            }
                        }
                    }

                    allMessages.AddRange(updates.ToAgentRunResponse().Messages);

                    ResetUserToAssistantForChangedRoles(roleChanges);

                    await context.SendMessageAsync(new HandoffState(handoffState.TurnToken, requestedHandoff, allMessages), cancellationToken: cancellationToken).ConfigureAwait(false);

                    async Task AddUpdateAsync(AgentRunResponseUpdate update, CancellationToken cancellationToken)
                    {
                        updates.Add(update);
                        if (handoffState.TurnToken.EmitEvents is true)
                        {
                            await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
                        }
                    }
                });

            public ValueTask ResetAsync() => default;
        }

        private sealed record class HandoffState(
            TurnToken TurnToken,
            string? InvokedHandoff,
            List<ChatMessage> Messages);
    }

    /// <summary>
    /// A manager that manages the flow of a group chat.
    /// </summary>
    public abstract class GroupChatManager
    {
        private int _maximumIterationCount = 40;

        /// <summary>
        /// Initializes a new instance of the <see cref="GroupChatManager"/> class.
        /// </summary>
        protected GroupChatManager() { }

        /// <summary>
        /// Gets the number of iterations in the group chat so far.
        /// </summary>
        public int IterationCount { get; internal set; }

        /// <summary>
        /// Gets or sets the maximum number of iterations allowed.
        /// </summary>
        /// <remarks>
        /// Each iteration involves a single interaction with a participating agent.
        /// The default is 40.
        /// </remarks>
        public int MaximumIterationCount
        {
            get => this._maximumIterationCount;
            set => this._maximumIterationCount = Throw.IfLessThan(value, 1);
        }

        /// <summary>
        /// Selects the next agent to participate in the group chat based on the provided chat history and team.
        /// </summary>
        /// <param name="history">The chat history to consider.</param>
        /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
        /// The default is <see cref="CancellationToken.None"/>.</param>
        /// <returns>The next <see cref="AIAgent"/> to speak. This agent must be part of the chat.</returns>
        protected internal abstract ValueTask<AIAgent> SelectNextAgentAsync(
            IReadOnlyList<ChatMessage> history,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Filters the chat history before it's passed to the next agent.
        /// </summary>
        /// <param name="history">The chat history to filter.</param>
        /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
        /// The default is <see cref="CancellationToken.None"/>.</param>
        /// <returns>The filtered chat history.</returns>
        protected internal virtual ValueTask<IEnumerable<ChatMessage>> UpdateHistoryAsync(
            IReadOnlyList<ChatMessage> history,
            CancellationToken cancellationToken = default) =>
            new(history);

        /// <summary>
        /// Determines whether the group chat should be terminated based on the provided chat history and iteration count.
        /// </summary>
        /// <param name="history">The chat history to consider.</param>
        /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
        /// The default is <see cref="CancellationToken.None"/>.</param>
        /// <returns>A <see cref="bool"/> indicating whether the chat should be terminated.</returns>
        protected internal virtual ValueTask<bool> ShouldTerminateAsync(
            IReadOnlyList<ChatMessage> history,
            CancellationToken cancellationToken = default) =>
            new(this.MaximumIterationCount is int max && this.IterationCount >= max);

        /// <summary>
        /// Resets the state of the manager for a new group chat session.
        /// </summary>
        protected internal virtual void Reset()
        {
            this.IterationCount = 0;
        }
    }

    /// <summary>
    /// Provides a <see cref="GroupChatManager"/> that selects agents in a round-robin fashion.
    /// </summary>
    public class RoundRobinGroupChatManager : GroupChatManager
    {
        private readonly IReadOnlyList<AIAgent> _agents;
        private readonly Func<RoundRobinGroupChatManager, IEnumerable<ChatMessage>, CancellationToken, ValueTask<bool>>? _shouldTerminateFunc;
        private int _nextIndex;

        /// <summary>
        /// Initializes a new instance of the <see cref="RoundRobinGroupChatManager"/> class.
        /// </summary>
        /// <param name="agents">The agents to be managed as part of this workflow.</param>
        /// <param name="shouldTerminateFunc">
        /// An optional function that determines whether the group chat should terminate based on the chat history
        /// before factoring in the default behavior, which is to terminate based only on the iteration count.
        /// </param>
        public RoundRobinGroupChatManager(
            IReadOnlyList<AIAgent> agents,
            Func<RoundRobinGroupChatManager, IEnumerable<ChatMessage>, CancellationToken, ValueTask<bool>>? shouldTerminateFunc = null)
        {
            Throw.IfNullOrEmpty(agents);
            foreach (var agent in agents)
            {
                Throw.IfNull(agent, nameof(agents));
            }

            this._agents = agents;
            this._shouldTerminateFunc = shouldTerminateFunc;
        }

        /// <inheritdoc />
        protected internal override ValueTask<AIAgent> SelectNextAgentAsync(
            IReadOnlyList<ChatMessage> history, CancellationToken cancellationToken = default)
        {
            AIAgent nextAgent = this._agents[this._nextIndex];

            this._nextIndex = (this._nextIndex + 1) % this._agents.Count;

            return new ValueTask<AIAgent>(nextAgent);
        }

        /// <inheritdoc />
        protected internal override async ValueTask<bool> ShouldTerminateAsync(
            IReadOnlyList<ChatMessage> history, CancellationToken cancellationToken = default)
        {
            if (this._shouldTerminateFunc is { } func && await func(this, history, cancellationToken).ConfigureAwait(false))
            {
                return true;
            }

            return await base.ShouldTerminateAsync(history, cancellationToken).ConfigureAwait(false);
        }

        /// <inheritdoc />
        protected internal override void Reset()
        {
            base.Reset();
            this._nextIndex = 0;
        }
    }

    /// <summary>
    /// Provides a builder for specifying group chat relationships between agents and building the resulting workflow.
    /// </summary>
    public sealed class GroupChatWorkflowBuilder
    {
        private readonly Func<IReadOnlyList<AIAgent>, GroupChatManager> _managerFactory;
        private readonly HashSet<AIAgent> _participants = new(AIAgentIDEqualityComparer.Instance);

        internal GroupChatWorkflowBuilder(Func<IReadOnlyList<AIAgent>, GroupChatManager> managerFactory) =>
            this._managerFactory = managerFactory;

        /// <summary>
        /// Adds the specified <paramref name="agents"/> as participants to the group chat workflow.
        /// </summary>
        /// <param name="agents">The agents to add as participants.</param>
        /// <returns>This instance of the <see cref="GroupChatWorkflowBuilder"/>.</returns>
        public GroupChatWorkflowBuilder AddParticipants(params IEnumerable<AIAgent> agents)
        {
            Throw.IfNull(agents);

            foreach (var agent in agents)
            {
                if (agent is null)
                {
                    Throw.ArgumentNullException(nameof(agents), "One or more target agents are null.");
                }

                this._participants.Add(agent);
            }

            return this;
        }

        /// <summary>
        /// Builds a <see cref="Workflow"/> composed of agents that operate via group chat, with the next
        /// agent to process messages selected by the group chat manager.
        /// </summary>
        /// <returns>The workflow built based on the group chat in the builder.</returns>
        public Workflow Build()
        {
            AIAgent[] agents = this._participants.ToArray();
            Dictionary<AIAgent, ExecutorIsh> agentMap = agents.ToDictionary(a => a, a => (ExecutorIsh)new AgentRunStreamingExecutor(a, includeInputInOutput: true));

            GroupChatHost host = new(agents, agentMap, this._managerFactory);

            WorkflowBuilder builder = new(host);

            foreach (var participant in agentMap.Values)
            {
                builder
                    .AddEdge(host, participant)
                    .AddEdge(participant, host);
            }

            return builder.WithOutputFrom(host).Build();
        }

        private sealed class GroupChatHost(AIAgent[] agents, Dictionary<AIAgent, ExecutorIsh> agentMap, Func<IReadOnlyList<AIAgent>, GroupChatManager> managerFactory) : Executor("GroupChatHost"), IResettableExecutor
        {
            private readonly AIAgent[] _agents = agents;
            private readonly Dictionary<AIAgent, ExecutorIsh> _agentMap = agentMap;
            private readonly Func<IReadOnlyList<AIAgent>, GroupChatManager> _managerFactory = managerFactory;
            private readonly List<ChatMessage> _pendingMessages = [];

            private GroupChatManager? _manager;

            protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) => routeBuilder
                .AddHandler<string>((message, context, _) => this._pendingMessages.Add(new(ChatRole.User, message)))
                .AddHandler<ChatMessage>((message, context, _) => this._pendingMessages.Add(message))
                .AddHandler<IEnumerable<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))
                .AddHandler<ChatMessage[]>((messages, _, __) => this._pendingMessages.AddRange(messages)) // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
                .AddHandler<List<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))  // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
                .AddHandler<TurnToken>(async (token, context, cancellationToken) =>
                {
                    List<ChatMessage> messages = [.. this._pendingMessages];
                    this._pendingMessages.Clear();

                    this._manager ??= this._managerFactory(this._agents);

                    if (!await this._manager.ShouldTerminateAsync(messages, cancellationToken).ConfigureAwait(false))
                    {
                        var filtered = await this._manager.UpdateHistoryAsync(messages, cancellationToken).ConfigureAwait(false);
                        messages = filtered is null || ReferenceEquals(filtered, messages) ? messages : [.. filtered];

                        if (await this._manager.SelectNextAgentAsync(messages, cancellationToken).ConfigureAwait(false) is AIAgent nextAgent &&
                            this._agentMap.TryGetValue(nextAgent, out var executor))
                        {
                            this._manager.IterationCount++;
                            await context.SendMessageAsync(messages, executor.Id, cancellationToken).ConfigureAwait(false);
                            await context.SendMessageAsync(token, executor.Id, cancellationToken).ConfigureAwait(false);
                            return;
                        }
                    }

                    this._manager = null;
                    await context.YieldOutputAsync(messages, cancellationToken).ConfigureAwait(false);
                });

            public ValueTask ResetAsync()
            {
                this._pendingMessages.Clear();
                this._manager = null;

                return default;
            }
        }
    }

    /// <summary>
    /// Iterates through <paramref name="messages"/> looking for <see cref="ChatRole.Assistant"/> messages and swapping
    /// any that have a different <see cref="ChatMessage.AuthorName"/> from <paramref name="targetAgentName"/> to <see cref="ChatRole.User"/>.
    /// </summary>
    private static List<ChatMessage>? ChangeAssistantToUserForOtherParticipants(string targetAgentName, List<ChatMessage> messages)
    {
        List<ChatMessage>? roleChanged = null;
        foreach (var m in messages)
        {
            if (m.Role == ChatRole.Assistant &&
                m.AuthorName != targetAgentName &&
                m.Contents.All(c => c is TextContent or DataContent or UriContent or UsageContent))
            {
                m.Role = ChatRole.User;
                (roleChanged ??= []).Add(m);
            }
        }

        return roleChanged;
    }

    /// <summary>
    /// Undoes changes made by <see cref="ChangeAssistantToUserForOtherParticipants(string, List{ChatMessage})"/>
    /// when passed the list of changes made by that method.
    /// </summary>
    private static void ResetUserToAssistantForChangedRoles(List<ChatMessage>? roleChanged)
    {
        if (roleChanged is not null)
        {
            foreach (var m in roleChanged)
            {
                m.Role = ChatRole.Assistant;
            }
        }
    }

    /// <summary>Derives from an agent a unique but also hopefully descriptive name that can be used as an executor's name or in a function name.</summary>
    private static string GetDescriptiveIdFromAgent(AIAgent agent)
    {
        string id = string.IsNullOrEmpty(agent.Name) ? agent.Id : $"{agent.Name}_{agent.Id}";
        return InvalidNameCharsRegex().Replace(id, "_");
    }

    /// <summary>Regex that flags any character other than ASCII digits or letters or the underscore.</summary>
#if NET
    [GeneratedRegex("[^0-9A-Za-z_]+")]
    private static partial Regex InvalidNameCharsRegex();
#else
    private static Regex InvalidNameCharsRegex() => s_invalidNameCharsRegex;
    private static readonly Regex s_invalidNameCharsRegex = new("[^0-9A-Za-z_]+", RegexOptions.Compiled);
#endif

    private sealed class AIAgentIDEqualityComparer : IEqualityComparer<AIAgent>
    {
        public static AIAgentIDEqualityComparer Instance { get; } = new();
        public bool Equals(AIAgent? x, AIAgent? y) => x?.Id == y?.Id;
        public int GetHashCode([DisallowNull] AIAgent obj) => obj?.GetHashCode() ?? 0;
    }
}
