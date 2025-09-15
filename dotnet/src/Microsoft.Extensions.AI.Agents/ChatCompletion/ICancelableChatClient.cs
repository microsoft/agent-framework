// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a chat client that supports cancellation of response.
/// </summary>
public interface ICancelableChatClient
{
    /// <summary>
    /// Cancels a response.
    /// </summary>
    /// <param name="id">The unique identifier of the response to cancel.</param>
    /// <param name="options">Optional parameters for cancelling the response.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>The <see cref="ChatResponse"/> representing result of the cancellation if supported; otherwise, <see langword="null"/>.</returns>
    Task<ChatResponse?> CancelResponseAsync(string id, CancelResponseOptions? options = null, CancellationToken cancellationToken = default);
}
