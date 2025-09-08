// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a chat client that supports long-running operations.
/// </summary>
/// <remarks>
/// Alternative names suggested by AI:
///     ILongRunningChatClient  - Emphasizes the long-running nature of the operations
///     IAsyncChatClient        - Highlights the asynchronous, non-immediate execution model
///     IPersistentChatClient   - Suggests operations that persist beyond immediate execution
///	    IResumableChatClient    - Emphasizes the ability to resume/manage operations that can be paused or resumed
///	    IBackgroundChatClient   - Indicates chat operations that run in the background and can be managed
///	    IJobChatClient          - Treats operations as jobs that can be managed
///	    ITaskChatClient         - Represents operations as tasks that can be managed
/// </remarks>
public interface ILongRunningChatClient : IChatClient
{
    /// <summary>
    /// Cancels a long-running chat operation.
    /// </summary>
    /// <param name="id">The unique identifier of the long-running operation to cancel.</param>
    /// <param name="options">Optional parameters for cancelling the long-running operation.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>The <see cref="ChatResponse"/> representing result of the cancellation if supported; otherwise, <see langword="null"/>.</returns>
    Task<ChatResponse?> CancelRunAsync(string id, ChatCancelRunOptions? options = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes a long-running chat operation.
    /// </summary>
    /// <param name="id">The unique identifier of the long-running operation to delete.</param>
    /// <param name="options">Optional parameters for deleting the long-running operation.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>The <see cref="ChatResponse"/> representing result of the cancellation if supported; otherwise, <see langword="null"/>.</returns>
    Task<ChatResponse?> DeleteRunAsync(string id, ChatDeleteRunOptions? options = null, CancellationToken cancellationToken = default);
}
