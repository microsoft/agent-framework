// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A <see cref="AIContextProvider"/> that applies a <see cref="CompactionStrategy"/> to compact
/// the message list before each agent invocation.
/// </summary>
/// <remarks>
/// <para>
/// This provider performs in-run compaction by organizing messages into atomic groups (preserving
/// tool-call/result pairings) before applying compaction logic. Only included messages are forwarded
/// to the agent's underlying chat client.
/// </para>
/// <para>
/// The <see cref="CompactionProvider"/> can be added to an agent's context provider pipeline
/// via <see cref="ChatClientAgentOptions.AIContextProviders"/> or via <c>UseAIContextProviders</c>
/// on a <see cref="ChatClientBuilder"/> or <see cref="AIAgentBuilder"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class CompactionProvider : AIContextProvider
{
    private readonly CompactionStrategy _compactionStrategy;
    private readonly ProviderSessionState<State> _sessionState;
    private readonly ILoggerFactory? _loggerFactory;

    /// <summary>
    /// Initializes a new instance of the <see cref="CompactionProvider"/> class.
    /// </summary>
    /// <param name="compactionStrategy">The compaction strategy to apply before each invocation.</param>
    /// <param name="stateKey">
    /// An optional key used to store the provider state in the <see cref="AgentSession.StateBag"/>.  Provide
    /// an explicit value if configuring multiple agents with different compaction strategies that will interact
    /// in the same session.
    /// </param>
    /// <param name="loggerFactory">
    /// An optional <see cref="ILoggerFactory"/> used to create a logger for provider diagnostics.
    /// When <see langword="null"/>, logging is disabled.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="compactionStrategy"/> is <see langword="null"/>.</exception>
    public CompactionProvider(CompactionStrategy compactionStrategy, string? stateKey = null, ILoggerFactory? loggerFactory = null)
    {
        this._compactionStrategy = Throw.IfNull(compactionStrategy);
        stateKey ??= this._compactionStrategy.GetType().Name;
        this.StateKeys = [stateKey];
        this._sessionState = new ProviderSessionState<State>(
            _ => new State(),
            stateKey,
            AgentJsonUtilities.DefaultOptions);
        this._loggerFactory = loggerFactory;
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys { get; }

    /// <summary>
    /// Applies compaction strategy to the provided message list and returns the compacted messages.
    /// This can be used for ad-hoc compaction outside of the provider pipeline.
    /// </summary>
    /// <param name="compactionStrategy">The compaction strategy to apply before each invocation.</param>
    /// <param name="messages">The messages to compact</param>
    /// <param name="logger">An optional <see cref="ILogger"/> for emitting compaction diagnostics.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>An enumeration of the compacted <see cref="ChatMessage"/> instances.</returns>
    public static async Task<IEnumerable<ChatMessage>> CompactAsync(CompactionStrategy compactionStrategy, IEnumerable<ChatMessage> messages, ILogger? logger = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(compactionStrategy);
        Throw.IfNull(messages);

        List<ChatMessage> messageList = messages as List<ChatMessage> ?? [.. messages];
        CompactionMessageIndex messageIndex = CompactionMessageIndex.Create(messageList);

        await compactionStrategy.CompactAsync(messageIndex, logger, cancellationToken).ConfigureAwait(false);

        return messageIndex.GetIncludedMessages();
    }

    /// <summary>
    /// Applies the compaction strategy to the accumulated message list before forwarding it to the agent.
    /// </summary>
    /// <param name="context">Contains the request context including all accumulated messages.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains an <see cref="AIContext"/>
    /// with the compacted message list.
    /// </returns>
    protected override async ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        using Activity? activity = CompactionTelemetry.ActivitySource.StartActivity(CompactionTelemetry.ActivityNames.CompactionProviderInvoke);

        ILoggerFactory loggerFactory = this.GetLoggerFactory(context.Agent);
        ILogger logger = loggerFactory.CreateLogger<CompactionProvider>();

        AgentSession? session = context.Session;
        IEnumerable<ChatMessage>? allMessages = context.AIContext.Messages;

        if (session is null || allMessages is null)
        {
            logger.LogCompactionProviderSkipped("no session or no messages");
            return context.AIContext;
        }

        ChatClientAgentSession? chatClientSession = session.GetService<ChatClientAgentSession>();
        if (chatClientSession is not null &&
            !string.IsNullOrWhiteSpace(chatClientSession.ConversationId))
        {
            logger.LogCompactionProviderSkipped("session managed by remote service");
            return context.AIContext;
        }

        List<ChatMessage> messageList = allMessages as List<ChatMessage> ?? [.. allMessages];

        State state = this._sessionState.GetOrInitializeState(session);

        CompactionMessageIndex messageIndex;
        if (state.MessageGroups.Count > 0)
        {
            messageIndex = new([.. state.MessageGroups]);

            // Treat all messages already in the index as chat history.
            foreach (var message in messageIndex.Groups.SelectMany(x => x.Messages))
            {
                message.AdditionalProperties ??= new AdditionalPropertiesDictionary();
                message.AdditionalProperties[AgentRequestMessageSourceAttribution.AdditionalPropertiesKey] =
                    new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, this.GetType().FullName!);
            }

            // Update existing index with any new messages appended since the last call.
            messageIndex.Update(messageList);
        }
        else
        {
            // First pass — initialize the message index from scratch.
            messageIndex = CompactionMessageIndex.Create(messageList);
        }

        string strategyName = this._compactionStrategy.GetType().Name;
        int beforeMessages = messageIndex.IncludedMessageCount;
        logger.LogCompactionProviderApplying(beforeMessages, strategyName);

        // Apply compaction
        await this._compactionStrategy.CompactAsync(
            messageIndex,
            loggerFactory.CreateLogger(this._compactionStrategy.GetType()),
            cancellationToken).ConfigureAwait(false);

        int afterMessages = messageIndex.IncludedMessageCount;
        if (afterMessages < beforeMessages)
        {
            logger.LogCompactionProviderApplied(beforeMessages, afterMessages);
        }

        // Persist the index
        state.MessageGroups.Clear();
        state.MessageGroups.AddRange(messageIndex.Groups);

        // Treat any messages that were generated by the compaction strategies as chat history.
        // This is to avoid adding them to chat history at the end of the run, which we don't want
        // since they may be summaries of previous messages that are already in chat history.
        foreach (var message in messageIndex.Groups.SelectMany(x => x.Messages))
        {
            // Only consider messages that aren't already marked as ChatHistory and messages that weren't passed into the provider.
            if (message.GetAgentRequestMessageSourceType() != AgentRequestMessageSourceType.ChatHistory && !messageList.Any(x => x.ContentEquals(message)))
            {
                message.AdditionalProperties ??= new AdditionalPropertiesDictionary();
                message.AdditionalProperties[AgentRequestMessageSourceAttribution.AdditionalPropertiesKey] =
                    new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, this.GetType().FullName!);
            }
        }

        return new AIContext
        {
            Instructions = context.AIContext.Instructions,
            Messages = messageIndex.GetIncludedMessages(),
            Tools = context.AIContext.Tools
        };
    }

    private ILoggerFactory GetLoggerFactory(AIAgent agent) =>
        this._loggerFactory ??
        agent.GetService<IChatClient>()?.GetService<ILoggerFactory>() ??
        NullLoggerFactory.Instance;

    /// <summary>
    /// Represents the persisted state of a <see cref="CompactionProvider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    internal sealed class State
    {
        /// <summary>
        /// Gets or sets the message index groups used for incremental compaction updates.
        /// </summary>
        [JsonPropertyName("messagegroups")]
        public List<CompactionMessageGroup> MessageGroups { get; set; } = [];
    }
}
