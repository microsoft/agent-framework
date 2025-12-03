// Copyright (c) Microsoft. All rights reserved.

using Google.Apis.Util;
using Google.GenAI;

namespace Microsoft.Extensions.AI;

/// <summary>Provides implementations of Microsoft.Extensions.AI abstractions based on <see cref="Client"/>.</summary>
public static class GoogleGenAIExtensions
{
    /// <summary>
    /// Creates an <see cref="IChatClient"/> wrapper around the specified <see cref="Client"/>.
    /// </summary>
    /// <param name="client">The <see cref="Client"/> to wrap.</param>
    /// <param name="defaultModelId">The default model ID to use for chat requests if not specified in <see cref="ChatOptions.ModelId"/>.</param>
    /// <returns>An <see cref="IChatClient"/> that wraps the specified client.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="client"/> is <see langword="null"/>.</exception>
    public static IChatClient AsIChatClient(this Client client, string? defaultModelId = null)
    {
        Utilities.ThrowIfNull(client, nameof(client));
        return new GoogleGenAIChatClient(client, defaultModelId);
    }

    /// <summary>
    /// Creates an <see cref="IChatClient"/> wrapper around the specified <see cref="Models"/>.
    /// </summary>
    /// <param name="models">The <see cref="Models"/> client to wrap.</param>
    /// <param name="defaultModelId">The default model ID to use for chat requests if not specified in <see cref="ChatOptions.ModelId"/>.</param>
    /// <returns>An <see cref="IChatClient"/> that wraps the specified <see cref="Models"/> client.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="models"/> is <see langword="null"/>.</exception>
    public static IChatClient AsIChatClient(this Models models, string? defaultModelId = null)
    {
        Utilities.ThrowIfNull(models, nameof(models));
        return new GoogleGenAIChatClient(models, defaultModelId);
    }
}
