// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;

namespace SampleApp;

/// <summary>
/// A <see cref="ChatHistoryProvider"/> that keeps a bounded window of recent messages in session state
/// (via <see cref="InMemoryChatHistoryProvider"/>) and overflows older messages to a vector store
/// (via <see cref="ChatHistoryMemoryProvider"/>). When providing chat history, it searches the vector
/// store for relevant older messages and prepends them as a memory context message.
/// </summary>
/// <remarks>
/// Only non-system messages are counted towards the session state limit and overflow mechanism. System messages are always retained in session state and are not included in the vector store.
/// Function calls and function results are also dropped when truncation happens, both from in-memory state, and they are also not persisted to the vector store.
/// </remarks>
internal sealed class BoundedChatHistoryProvider : ChatHistoryProvider, IDisposable
{
    private readonly InMemoryChatHistoryProvider _chatHistoryProvider;
    private readonly ChatHistoryMemoryProvider _memoryProvider;
    private readonly TruncatingChatReducer _reducer;
    private readonly string _contextPrompt;
    private IReadOnlyList<string>? _stateKeys;

    /// <summary>
    /// Initializes a new instance of the <see cref="BoundedChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="maxSessionMessages">The maximum number of non-system messages to keep in session state before overflowing to the vector store.</param>
    /// <param name="vectorStore">The vector store to use for storing and retrieving overflow chat history.</param>
    /// <param name="collectionName">The name of the collection for storing overflow chat history in the vector store.</param>
    /// <param name="vectorDimensions">The number of dimensions to use for the chat history vector store embeddings.</param>
    /// <param name="stateInitializer">A delegate that initializes the memory provider state, providing the storage and search scopes.</param>
    /// <param name="contextPrompt">Optional prompt to prefix memory search results. Defaults to a standard memory context prompt.</param>
    public BoundedChatHistoryProvider(
        int maxSessionMessages,
        VectorStore vectorStore,
        string collectionName,
        int vectorDimensions,
        Func<AgentSession?, ChatHistoryMemoryProvider.State> stateInitializer,
        string? contextPrompt = null)
    {
        if (maxSessionMessages < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxSessionMessages), "maxSessionMessages must be non-negative.");
        }

        this._reducer = new TruncatingChatReducer(maxSessionMessages);
        this._chatHistoryProvider = new InMemoryChatHistoryProvider(new InMemoryChatHistoryProviderOptions
        {
            ChatReducer = this._reducer,
            ReducerTriggerEvent = InMemoryChatHistoryProviderOptions.ChatReducerTriggerEvent.AfterMessageAdded,
            StorageInputRequestMessageFilter = msgs => msgs,
        });
        this._memoryProvider = new ChatHistoryMemoryProvider(
            vectorStore,
            collectionName,
            vectorDimensions,
            stateInitializer,
            options: new ChatHistoryMemoryProviderOptions
            {
                SearchInputMessageFilter = msgs => msgs,
                StorageInputRequestMessageFilter = msgs => msgs,
            });
        this._contextPrompt = contextPrompt
            ?? "The following are memories from earlier in this conversation. Use them to inform your responses:";
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= this._chatHistoryProvider.StateKeys.Concat(this._memoryProvider.StateKeys).ToArray();

    /// <inheritdoc />
    protected override async ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(
        InvokingContext context,
        CancellationToken cancellationToken = default)
    {
        // Delegate to the inner provider's full lifecycle (retrieve, filter, stamp, merge with request messages).
        var chatHistoryProviderInputContext = new InvokingContext(context.Agent, context.Session, []);
        var allMessages = await this._chatHistoryProvider.InvokingAsync(chatHistoryProviderInputContext, cancellationToken).ConfigureAwait(false);

        // Search the vector store for relevant older messages.
        var aiContext = new AIContext { Messages = context.RequestMessages.ToList() };
        var invokingContext = new AIContextProvider.InvokingContext(
            context.Agent, context.Session, aiContext);

        var result = await this._memoryProvider.InvokingAsync(invokingContext, cancellationToken).ConfigureAwait(false);

        // Extract only the messages added by the memory provider (stamped with AIContextProvider source type).
        var memoryMessages = result.Messages?
            .Where(m => m.GetAgentRequestMessageSourceType() == AgentRequestMessageSourceType.AIContextProvider)
            .ToList();

        if (memoryMessages is { Count: > 0 })
        {
            var memoryText = string.Join("\n", memoryMessages.Select(m => m.Text).Where(t => !string.IsNullOrWhiteSpace(t)));

            if (!string.IsNullOrWhiteSpace(memoryText))
            {
                var contextMessage = new ChatMessage(ChatRole.User, $"{this._contextPrompt}\n{memoryText}");
                return new[] { contextMessage }.Concat(allMessages);
            }
        }

        return allMessages;
    }

    /// <inheritdoc />
    protected override async ValueTask StoreChatHistoryAsync(
        InvokedContext context,
        CancellationToken cancellationToken = default)
    {
        // Delegate storage to the in-memory provider. Its TruncatingChatReducer (AfterMessageAdded trigger)
        // will automatically truncate to the configured maximum and expose any removed messages.
        var innerContext = new InvokedContext(
            context.Agent, context.Session, context.RequestMessages, context.ResponseMessages!);
        await this._chatHistoryProvider.InvokedAsync(innerContext, cancellationToken).ConfigureAwait(false);

        // Archive any messages that the reducer removed to the vector store.
        if (this._reducer.RemovedMessages is { Count: > 0 })
        {
            var overflowContext = new AIContextProvider.InvokedContext(
                context.Agent, context.Session, this._reducer.RemovedMessages, []);
            await this._memoryProvider.InvokedAsync(overflowContext, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        this._memoryProvider.Dispose();
    }
}
