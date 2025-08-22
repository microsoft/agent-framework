// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.UnitTests.Sample;

internal static class Step6EntryPoint
{
    public static Workflow<List<ChatMessage>> CreateWorkflow(int maxTurns)
    {
        GroupChatBuilder builder =
            GroupChatBuilder.Create<RoundRobinGroupChatManager, RoundRobinGroupChatManagerOptions>
                                (options => options.MaxTurns = maxTurns)
                            .AddParticipant(new HelloAgent(), shouldEmitEvents: true)
                            .AddParticipant(new EchoAgent(), shouldEmitEvents: true);

        return builder.ReduceToWorkflow();
    }

    public static async ValueTask RunAsync(TextWriter writer, int maxSteps = 2)
    {
        Workflow<List<ChatMessage>> workflow = CreateWorkflow(maxSteps);

        StreamingRun run = await InProcessExecution.StreamAsync(workflow, [])
                                                   .ConfigureAwait(false);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompleteEvent executorComplete)
            {
                Debug.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
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

    private sealed class RoundRobinGroupChatManagerOptions : GroupChatManagerOptions
    {
        public int? MaxTurns { get; set; } = null;
    }

    private sealed class RoundRobinGroupChatManager() : GroupChatManager<RoundRobinGroupChatManagerOptions>
    {
        public int TurnCount { get; private set; } = 0;
        public int? MaxTurns { get; private set; } = null;

        protected internal override void Configure(RoundRobinGroupChatManagerOptions options)
        {
            base.Configure(options);

            this.MaxTurns = options.MaxTurns;
        }

        public override int? GetNextTurnExecutor(GroupChatHistory history)
        {
            if (this.ParticipantIds.Length == 0)
            {
                throw new InvalidOperationException("No participants in the group chat.");
            }

            if (this.TurnCount >= this.MaxTurns)
            {
                return null;
            }

            return this.TurnCount++ % this.ParticipantIds.Length;
        }
    }
}

internal sealed class HelloAgent(string id = nameof(HelloAgent)) : AIAgent
{
    public const string Greeting = "Hello World!";
    public const string DefaultId = nameof(HelloAgent);

    public override string Id => id;
    public override string? Name => id;

    public override async Task<AgentRunResponse> RunAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        IEnumerable<AgentRunResponseUpdate> update = [
            await this.RunStreamingAsync(messages, thread, options, cancellationToken)
                      .SingleAsync(cancellationToken)
                      .ConfigureAwait(false)];

        return update.ToAgentRunResponse();
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        AgentRunResponseUpdate response = new(ChatRole.Assistant, "Hello World!")
        {
            AgentId = this.Id,
            AuthorName = this.Name,
        };

        yield return response;
    }
}

internal sealed class EchoAgent(string id = nameof(EchoAgent)) : AIAgent
{
    public const string Prefix = "You said: ";
    public const string DefaultId = nameof(EchoAgent);

    public override string Id => id;
    public override string? Name => id;

    public override async Task<AgentRunResponse> RunAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        IEnumerable<AgentRunResponseUpdate> update = [
            await this.RunStreamingAsync(messages, thread, options, cancellationToken)
                      .SingleAsync(cancellationToken)
                      .ConfigureAwait(false)];

        return update.ToAgentRunResponse();
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (messages.Count == 0)
        {
            throw new ArgumentException("No messages provided to echo.", nameof(messages));
        }

        StringBuilder collectedText = new(Prefix);
        foreach (string messageText in messages.Select(message => message.Text)
                                               .Where(text => !string.IsNullOrEmpty(text)))
        {
            collectedText.AppendLine(messageText);
        }

        AgentRunResponseUpdate result = new(ChatRole.Assistant, collectedText.ToString())
        {
            AgentId = this.Id,
            AuthorName = this.Name,
        };

        yield return result;
    }
}

internal sealed class GroupChatHistory
{
    private readonly List<ChatMessage> _messages = new();
    private int _bookmark = 0;

    public void AddMessage(ChatMessage message)
    {
        this._messages.Add(message);
    }

    public void AddMessages(IEnumerable<ChatMessage> messages)
    {
        this._messages.AddRange(messages);
    }

    public void UpdateBookmark()
    {
        this._bookmark = this._messages.Count;
    }

    public IReadOnlyList<ChatMessage> FullHistory => this._messages.AsReadOnly();
    public IEnumerable<ChatMessage> NewMessagesThisTurn => this._messages.Skip(this._bookmark);
}

internal class GroupChatManagerOptions
{
}

internal abstract class GroupChatManager
{
    public string[] ParticipantIds { get; internal init; } = [];

    public abstract int? GetNextTurnExecutor(GroupChatHistory history);
}

internal abstract class GroupChatManager<TOptions> : GroupChatManager where TOptions : GroupChatManagerOptions, new()
{
    protected internal virtual void Configure(TOptions options) { }
}

internal sealed class GroupChatBuilder
{
    private readonly List<ExecutorIsh> _participants = new();
    private readonly List<bool> _shouldEmitEvents = new();
    private readonly Func<string[], GroupChatManager> _managerFactory;

    private GroupChatBuilder(Func<string[], GroupChatManager> managerFactory)
    {
        this._managerFactory = managerFactory;
    }

    public static GroupChatBuilder Create<TManager>() where TManager : GroupChatManager, new()
    {
        return new GroupChatBuilder(participantIds => new TManager() { ParticipantIds = participantIds });
    }

    public static GroupChatBuilder Create<TManager, TOptions>(Action<TOptions> configure)
        where TManager : GroupChatManager<TOptions>, new()
        where TOptions : GroupChatManagerOptions, new()
    {
        TOptions options = new();
        configure(options);

        return new GroupChatBuilder(participantIds =>
        {
            TManager manager = new() { ParticipantIds = participantIds };
            manager.Configure(options);
            return manager;
        });
    }

    public GroupChatBuilder AddParticipant(ExecutorIsh executor, bool shouldEmitEvents = false)
    {
        this._participants.Add(executor);
        this._shouldEmitEvents.Add(shouldEmitEvents);

        return this;
    }

    public GroupChatBuilder AddParticipants(params ExecutorIsh[] executors)
    {
        this._participants.AddRange(executors);
        return this;
    }

    public Workflow<List<ChatMessage>> ReduceToWorkflow()
    {
        string[] participantIds = this._participants.Select(identified => identified.Id).ToArray();
        GroupChatHost host = new(this._shouldEmitEvents.ToArray(), this._managerFactory(participantIds));

        WorkflowBuilder builder = new WorkflowBuilder(host)
                        .AddFanOutEdge(host, targets: this._participants.ToArray());

        foreach (ExecutorIsh participant in this._participants)
        {
            builder.AddEdge(participant, host);
        }

        return builder.Build<List<ChatMessage>>();

        //bool IsMessageType(object? message) => message is ChatMessage || message is IEnumerable<ChatMessage>;
    }

    private sealed class TurnAssignedEvent(string executorId, string nextSpeakerId) : ExecutorEvent(executorId, data: nextSpeakerId);

    private sealed class GroupChatHost : Executor
    {
        private readonly bool[] _shouldEmitEvents;
        private readonly GroupChatManager _manager;
        private readonly bool _autoStartConversation;

        private readonly GroupChatHistory _history = new();

        public GroupChatHost(bool[] shouldEmitEvents, GroupChatManager manager, bool autoStartConversation = false) : base(nameof(GroupChatHost))
        {
            this._shouldEmitEvents = shouldEmitEvents;
            this._manager = manager ?? throw new ArgumentNullException(nameof(manager));
            this._autoStartConversation = autoStartConversation;
        }

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
        {
            return routeBuilder.AddHandler<List<ChatMessage>>(this.HandleChatMessagesAsync)
                               .AddHandler<ChatMessage>(this.HandleChatMessageAsync)
                               .AddHandler<TurnToken>(this.AssignNextTurnAsync);
        }

        private async Task TryAutoStartConversationAsync(IWorkflowContext context)
        {
            if (this._autoStartConversation && this.TryEnterConversation())
            {
                await this.AssignNextTurnAsync(new TurnToken(emitEvents: false), context).ConfigureAwait(false);
            }
        }

        private async ValueTask HandleChatMessagesAsync(List<ChatMessage> initialMessages, IWorkflowContext context)
        {
            this._history.AddMessages(initialMessages);

            await context.SendMessageAsync(initialMessages).ConfigureAwait(false);
            await this.TryAutoStartConversationAsync(context).ConfigureAwait(false);
        }

        private async ValueTask HandleChatMessageAsync(ChatMessage message, IWorkflowContext context)
        {
            // First, add the message to the history, then forward to all executors
            this._history.AddMessage(message);

            await context.SendMessageAsync(message).ConfigureAwait(false);
            await this.TryAutoStartConversationAsync(context).ConfigureAwait(false);
        }

        private int _inConversationFlag = 0;

        /// <summary>
        /// Atomically switches to "in conversation" state if not already in that state.
        /// </summary>
        /// <returns><see langword="true"/> if the state was changed, <see langword="false"/> otherwise.</returns>
        private bool TryEnterConversation()
        {
            return Interlocked.CompareExchange(ref this._inConversationFlag, 1, 0) == 0;
        }

        private bool _shouldHostEmitEvents = false;
        private async ValueTask AssignNextTurnAsync(TurnToken token, IWorkflowContext context)
        {
            if (this.TryEnterConversation())
            {
                // Capture the initial turn token's EmitEvents setting
                this._shouldHostEmitEvents = token.EmitEvents.HasValue ? token.EmitEvents.Value : false;
            }

            int? nextSpeakerIndex = this._manager.GetNextTurnExecutor(this._history);
            if (nextSpeakerIndex == null)
            {
                await context.AddEventAsync(new WorkflowCompletedEvent())
                             .ConfigureAwait(false);

                return;
            }

            string nextSpeakerId = this._manager.ParticipantIds[nextSpeakerIndex.Value];

            if (this._shouldHostEmitEvents)
            {
                await context.AddEventAsync(new TurnAssignedEvent(this.Id, nextSpeakerId))
                             .ConfigureAwait(false);
            }

            await context.SendMessageAsync(new TurnToken(this._shouldEmitEvents[nextSpeakerIndex.Value]), nextSpeakerId)
                         .ConfigureAwait(false);
        }
    }
}
