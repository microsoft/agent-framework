// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI;

/// <summary>
/// TBD
/// </summary>
public interface INewRunnableChatClient : IChatClient
{
    /// <summary>
    /// TBD
    /// </summary>
    Task<ChatResponse> CancelRunAsync(string runId, CancellationToken cancellationToken = default);

    /// <summary>
    /// TBD
    /// </summary>
    Task<ChatResponse> DeleteRunAsync(string runId, CancellationToken cancellationToken = default);
}
