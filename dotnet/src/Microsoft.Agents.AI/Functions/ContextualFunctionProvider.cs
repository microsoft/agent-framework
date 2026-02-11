// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.VectorData;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Functions;

/// <summary>
/// Represents a contextual function provider that performs RAG (Retrieval-Augmented Generation) on the provided functions to identify
/// the most relevant functions for the current context. The provider vectorizes the provided function names and descriptions
/// and stores them in the specified vector store, allowing for a vector search to find the most relevant
/// functions for a given context and provide the functions to the AI model/agent.
/// </summary>
/// <remarks>
/// <list type="bullet">
/// <item>
/// The provider is designed to work with in-memory vector stores. Using other vector stores
/// will require the data synchronization and data lifetime management to be done by the caller.
/// </item>
/// <item>
/// The in-memory vector store is supposed to be created per provider and not shared between providers
/// unless each provider uses a different collection name. Not following this may lead to a situation
/// where one provider identifies a function belonging to another provider as relevant and, as a result,
/// an attempt to access it by the first provider will fail because the function is not registered with it.
/// </item>
/// <item>
/// The provider uses function name as a key for the records and as such the specified vector store
/// should support record keys of string type.
/// </item>
/// </list>
/// </remarks>
public sealed class ContextualFunctionProvider : AIContextProvider
{
    private readonly FunctionStore _functionStore;
    private readonly ConcurrentQueue<ChatMessage> _recentMessages = [];
    private readonly ContextualFunctionProviderOptions _options;
    private bool _areFunctionsVectorized;

    /// <summary>
    /// Initializes a new instance of the <see cref="ContextualFunctionProvider"/> class.
    /// </summary>
    /// <param name="vectorStore">An instance of a vector store.</param>
    /// <param name="vectorDimensions">The number of dimensions to use for the memory embeddings.</param>
    /// <param name="functions">The functions to vectorize and store for searching related functions.</param>
    /// <param name="maxNumberOfFunctions">The maximum number of relevant functions to retrieve from the vector store.</param>
    /// <param name="options">Further optional settings for configuring the provider.</param>
    /// <param name="loggerFactory">The logger factory to use for logging. If not provided, no logging will be performed.</param>
    public ContextualFunctionProvider(
        VectorStore vectorStore,
        int vectorDimensions,
        IEnumerable<AIFunction> functions,
        int maxNumberOfFunctions,
        ContextualFunctionProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : this(vectorStore, vectorDimensions, functions, maxNumberOfFunctions, default, options, null, loggerFactory)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ContextualFunctionProvider"/> class.
    /// </summary>
    /// <param name="vectorStore">An instance of a vector store.</param>
    /// <param name="vectorDimensions">The number of dimensions to use for the memory embeddings.</param>
    /// <param name="functions">The functions to vectorize and store for searching related functions.</param>
    /// <param name="maxNumberOfFunctions">The maximum number of relevant functions to retrieve from the vector store.</param>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized provider state.</param>
    /// <param name="options">Further optional settings for configuring the provider.</param>
    /// <param name="jsonSerializerOptions">Optional serializer options. If not provided, <see cref="AgentJsonUtilities.DefaultOptions"/> will be used.</param>
    /// <param name="loggerFactory">The logger factory to use for logging. If not provided, no logging will be performed.</param>
    public ContextualFunctionProvider(
        VectorStore vectorStore,
        int vectorDimensions,
        IEnumerable<AIFunction> functions,
        int maxNumberOfFunctions,
        JsonElement serializedState,
        ContextualFunctionProviderOptions? options = null,
        JsonSerializerOptions? jsonSerializerOptions = null,
        ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(vectorStore);
        Throw.IfLessThan(vectorDimensions, 1, "Vector dimensions must be greater than 0");
        Throw.IfNull(functions);
        Throw.IfLessThan(maxNumberOfFunctions, 1, "Max number of functions must be greater than 0");

        this._options = options ?? new ContextualFunctionProviderOptions();
        Throw.IfLessThan(this._options.NumberOfRecentMessagesInContext, 1, "Number of recent messages to include into context must be greater than 0");

        this._functionStore = new FunctionStore(
            vectorStore,
            string.IsNullOrWhiteSpace(this._options.CollectionName) ? "functions" : this._options.CollectionName,
            vectorDimensions,
            functions,
            maxNumberOfFunctions,
            loggerFactory,
            options: new()
            {
                EmbeddingValueProvider = this._options.EmbeddingValueProvider,
            }
         );

        // Restore recent messages from serialized state if provided
        if (serializedState.ValueKind is not JsonValueKind.Null and not JsonValueKind.Undefined)
        {
            JsonSerializerOptions jso = jsonSerializerOptions ?? AgentJsonUtilities.DefaultOptions;
            ContextualFunctionProviderState? state = serializedState.Deserialize(jso.GetTypeInfo(typeof(ContextualFunctionProviderState))) as ContextualFunctionProviderState;
            if (state?.RecentMessages is { Count: > 0 })
            {
                // Restore recent messages respecting the limit (may truncate if limit changed afterwards).
                foreach (ChatMessage message in state.RecentMessages.Take(this._options.NumberOfRecentMessagesInContext))
                {
                    this._recentMessages.Enqueue(message);
                }
            }
        }
    }

    /// <inheritdoc />
    public override async ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);

        // Vectorize the functions if they are not already vectorized
        if (!this._areFunctionsVectorized)
        {
            await this._functionStore.SaveAsync(cancellationToken).ConfigureAwait(false);

            this._areFunctionsVectorized = true;
        }

        // Build the search context
        var searchContext = await this.BuildContextAsync(context.RequestMessages, cancellationToken).ConfigureAwait(false);

        // Get the function relevant to the context
        var functions = await this._functionStore
                .SearchAsync(searchContext, cancellationToken: cancellationToken)
                .ConfigureAwait(false);

        return new AIContext { Tools = [.. functions] };
    }

    /// <inheritdoc/>
    public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(context);

        // Don't add messages to the recent messages queue if the invocation failed
        if (context.InvokeException is not null)
        {
            return default;
        }

        // Add the request and response messages to the recent messages queue
        foreach (var message in context.RequestMessages)
        {
            this._recentMessages.Enqueue(message);
        }

        if (context.ResponseMessages is not null)
        {
            foreach (var message in context.ResponseMessages)
            {
                this._recentMessages.Enqueue(message);
            }
        }

        // If there are more messages than the configured limit, remove the oldest ones
        while (this._recentMessages.Count > this._options.NumberOfRecentMessagesInContext)
        {
            this._recentMessages.TryDequeue(out _);
        }

        return default;
    }

    /// <summary>
    /// Serializes the current provider state to a <see cref="JsonElement"/> containing the recent messages.
    /// </summary>
    /// <param name="jsonSerializerOptions">Optional serializer options. This parameter is not used; <see cref="AgentJsonUtilities.DefaultOptions"/> is always used for serialization.</param>
    /// <returns>A <see cref="JsonElement"/> with the recent messages, or default if there are no recent messages.</returns>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        ContextualFunctionProviderState state = new();
        if (this._options.NumberOfRecentMessagesInContext > 0 && !this._recentMessages.IsEmpty)
        {
            state.RecentMessages = this._recentMessages.Take(this._options.NumberOfRecentMessagesInContext).ToList();
        }

        return JsonSerializer.SerializeToElement(state, AgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ContextualFunctionProviderState)));
    }

    /// <summary>
    /// Builds the context from chat messages.
    /// </summary>
    /// <param name="newMessages">The new messages.</param>
    /// <param name="cancellationToken">The cancellation token to use for cancellation.</param>
    private async Task<string> BuildContextAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken)
    {
        if (this._options.ContextEmbeddingValueProvider is not null)
        {
            // Ensure we only take the recent messages up to the configured limit
            var recentMessages = this._recentMessages
                .Skip(Math.Max(0, this._recentMessages.Count - this._options.NumberOfRecentMessagesInContext));

            return await this._options.ContextEmbeddingValueProvider.Invoke(recentMessages, newMessages, cancellationToken).ConfigureAwait(false);
        }

        // Build context by concatenating the recent messages and the new messages
        return string.Join(
            Environment.NewLine,
            this._recentMessages
                .Skip(Math.Max(0, this._recentMessages.Count - this._options.NumberOfRecentMessagesInContext))
                .Concat(newMessages)
                .Where(m => !string.IsNullOrWhiteSpace(m?.Text))
                .Select(m => m.Text));
    }

    internal sealed class ContextualFunctionProviderState
    {
        public List<ChatMessage>? RecentMessages { get; set; }
    }
}
