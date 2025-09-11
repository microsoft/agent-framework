// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// An <see cref="AIContextProvider"/> that aggregates other <see cref="AIContextProvider"/> instances and delegates events to them.
/// </summary>
public sealed class AggregateAIContextProvider : AIContextProvider, IList<AIContextProvider>
{
    private readonly List<AIContextProvider> _providers = new();

    /// <inheritdoc />
    public override async ValueTask MessagesAddingAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        if (this._providers.Count == 0)
        {
            return;
        }

        // Notify all the sub providers of new messages in serial.
        foreach (var provider in this._providers)
        {
            cancellationToken.ThrowIfCancellationRequested();
            await provider.MessagesAddingAsync(newMessages, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <inheritdoc />
    public override async ValueTask<AIContext> InvokingAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        if (this._providers.Count == 0)
        {
            return new AIContext();
        }

        // Invoke all the sub providers in serial and
        // aggregate all the sub-contexts into a single context.
        List<AITool>? allTools = null;
        List<ChatMessage>? allMessages = null;
        StringBuilder? allInstructions = null;
        foreach (var provider in this._providers)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var subContext = await provider.InvokingAsync(newMessages, cancellationToken).ConfigureAwait(false);

            if (subContext == null)
            {
                continue;
            }

            if (subContext.Tools != null && subContext.Tools.Count > 0)
            {
                allTools ??= [];
                allTools.AddRange(subContext.Tools);
            }

            if (subContext.Messages != null && subContext.Messages.Count > 0)
            {
                allMessages ??= [];
                allMessages.AddRange(subContext.Messages);
            }

            if (!string.IsNullOrWhiteSpace(subContext.Instructions))
            {
                allInstructions ??= new StringBuilder();
                if (allInstructions.Length > 0)
                {
                    allInstructions.AppendLine();
                }
                allInstructions.Append(subContext.Instructions);
            }
        }

        var combinedContext = new AIContext
        {
            Tools = allTools,
            Messages = allMessages,
            Instructions = allInstructions?.ToString()
        };

        return combinedContext;
    }

    /// <inheritdoc />
    public override async ValueTask<JsonElement?> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (this._providers.Count == 0)
        {
            return default;
        }

        List<JsonElement?> subElements = new();
        foreach (var provider in this._providers)
        {
            cancellationToken.ThrowIfCancellationRequested();
            subElements.Add(await provider.SerializeAsync(jsonSerializerOptions, cancellationToken).ConfigureAwait(false));
        }

        return JsonSerializer.SerializeToElement(subElements, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(List<JsonElement?>)));
    }

    /// <inheritdoc />
    public override async ValueTask DeserializeAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (serializedState.ValueKind == JsonValueKind.Undefined || serializedState.ValueKind == JsonValueKind.Null)
        {
            return;
        }

        var state = JsonSerializer.Deserialize(
            serializedState,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(List<JsonElement?>))) as List<JsonElement?>;

        if (state == null)
        {
            return;
        }

        for (int i = 0; i < this._providers.Count; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var provider = this._providers[i];

            // We have more providers than we have state entries, so assume
            // that a new provider has been added and there is no state for it.
            if (i >= state.Count)
            {
                break;
            }

            var subState = state[i];
            if (subState == null)
            {
                continue;
            }

            await provider.DeserializeAsync(subState.Value, jsonSerializerOptions, cancellationToken).ConfigureAwait(false);
        }

        return;
    }

    /// <inheritdoc />
    public AIContextProvider this[int index] { get => this._providers[index]; set => this._providers[index] = value; }

    /// <inheritdoc />
    public int Count => this._providers.Count;

    /// <inheritdoc />
    public bool IsReadOnly => false;

    /// <inheritdoc />
    public void Add(AIContextProvider item) => this._providers.Add(item);

    /// <inheritdoc />
    public void Clear() => this._providers.Clear();

    /// <inheritdoc />
    public bool Contains(AIContextProvider item) => this._providers.Contains(item);

    /// <inheritdoc />
    public void CopyTo(AIContextProvider[] array, int arrayIndex) => this._providers.CopyTo(array, arrayIndex);

    /// <inheritdoc />
    public IEnumerator<AIContextProvider> GetEnumerator() => this._providers.GetEnumerator();

    /// <inheritdoc />
    public int IndexOf(AIContextProvider item) => this._providers.IndexOf(item);

    /// <inheritdoc />
    public void Insert(int index, AIContextProvider item) => this._providers.Insert(index, item);

    /// <inheritdoc />
    public bool Remove(AIContextProvider item) => this._providers.Remove(item);

    /// <inheritdoc />
    public void RemoveAt(int index) => this._providers.RemoveAt(index);

    /// <inheritdoc />
    IEnumerator IEnumerable.GetEnumerator() => this.GetEnumerator();
}
