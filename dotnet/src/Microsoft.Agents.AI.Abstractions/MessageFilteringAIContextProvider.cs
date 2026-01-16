// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> decorator that allows filtering the data
/// passed into and out of an inner <see cref="AIContextProvider"/>.
/// </summary>
public sealed class MessageFilteringAIContextProvider : AIContextProvider
{
    private readonly AIContextProvider _innerAIContextProvider;
    private readonly Func<AIContext, AIContext>? _invokingContextFilter;
    private readonly Func<InvokedContext, InvokedContext>? _invokedContextFilter;

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageFilteringAIContextProvider"/> class.
    /// </summary>
    /// <remarks>Use this constructor to customize how context is filtered before and after invocation by
    /// providing appropriate filter functions. If no filters are provided, the context provider operates without
    /// additional filtering.</remarks>
    /// <param name="innerAIContextProvider">The underlying AI context provider to be wrapped. Cannot be null.</param>
    /// <param name="invokingContextFilter">An optional filter function to apply to the AI context before it is returned. If null, no filter is applied at this
    /// stage.</param>
    /// <param name="invokedContextFilter">An optional filter function to apply to the invocation context before it is consumed. If null, no
    /// filter is applied at this stage.</param>
    /// <exception cref="ArgumentNullException">Thrown if innerAIContextProvider is null.</exception>
    public MessageFilteringAIContextProvider(
        AIContextProvider innerAIContextProvider,
        Func<AIContext, AIContext>? invokingContextFilter = null,
        Func<InvokedContext, InvokedContext>? invokedContextFilter = null)
    {
        this._innerAIContextProvider = Throw.IfNull(innerAIContextProvider);

        if (invokingContextFilter == null && invokedContextFilter == null)
        {
            throw new ArgumentException("At least one filter function, invokingContextFilter or invokedContextFilter, must be provided.");
        }

        this._invokingContextFilter = invokingContextFilter;
        this._invokedContextFilter = invokedContextFilter;
    }

    /// <inheritdoc />
    public override async ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var aiContext = await this._innerAIContextProvider.InvokingAsync(context, cancellationToken).ConfigureAwait(false);
        return this._invokingContextFilter != null ? this._invokingContextFilter(aiContext) : aiContext;
    }

    /// <inheritdoc />
    public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (this._invokedContextFilter != null)
        {
            context = this._invokedContextFilter(context);
        }

        return this._innerAIContextProvider.InvokedAsync(context, cancellationToken);
    }

    /// <inheritdoc />
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return this._innerAIContextProvider.Serialize(jsonSerializerOptions);
    }
}
