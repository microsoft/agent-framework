// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Delegating chat client that overwrites <see cref="ChatResponse.ModelId"/> and
/// <see cref="ChatResponseUpdate.ModelId"/> with the actual served model name captured by
/// <see cref="ServedModelPolicy"/> from the <c>x-ms-served-model</c> response header.
/// </summary>
/// <remarks>
/// <para>
/// Before each inner call, this client pushes a fresh <see cref="StrongBox{T}"/> onto
/// <see cref="ServedModelScope"/> so the <see cref="ServedModelPolicy"/> (running inside the
/// SCM pipeline) can write the header value into it. After the inner call returns, the client
/// reads the box and overwrites <see cref="ChatResponse.ModelId"/>. When the box is empty
/// (header absent on non-Azure endpoints), the original model name is preserved unchanged.
/// </para>
/// </remarks>
internal sealed class ServedModelChatClient : DelegatingChatClient
{
    public ServedModelChatClient(IChatClient innerClient)
        : base(innerClient)
    {
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var box = new StrongBox<string?>(null);
        ServedModelScope.Current = box;

        var response = await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);

        if (box.Value is { } servedModel)
        {
            response.ModelId = servedModel;
        }

        return response;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var box = new StrongBox<string?>(null);
        ServedModelScope.Current = box;

        await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
        {
            if (box.Value is { } servedModel)
            {
                update.ModelId = servedModel;
            }

            yield return update;
        }
    }
}
