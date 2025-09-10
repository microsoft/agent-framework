// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;
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
    public override async Task MessagesAddingAsync(IEnumerable<ChatMessage> newMessages, string? agentThreadId, CancellationToken cancellationToken = default)
    {
        if (this._providers.Count == 0)
        {
            return;
        }

        await Task.WhenAll(this._providers.Select(x => x.MessagesAddingAsync(newMessages, agentThreadId, cancellationToken))).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public override async Task<AIContext> ModelInvokingAsync(IEnumerable<ChatMessage> newMessages, string? agentThreadId, CancellationToken cancellationToken = default)
    {
        if (this._providers.Count == 0)
        {
            return new AIContext();
        }

        // Invoke the downstream providers in parallel.
        var subContexts = await Task.WhenAll(this._providers.Select(x => x.ModelInvokingAsync(newMessages, agentThreadId, cancellationToken))).ConfigureAwait(false);

        // Aggregate all the sub-contexts into a single context.
        List<AITool>? allTools = null;
        List<ChatMessage>? allMessages = null;
        StringBuilder? allInstructions = null;
        foreach (var subContext in subContexts)
        {
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
