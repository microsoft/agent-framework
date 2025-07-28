// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Specifies the possible storage locations for messages of <see cref="MessageStoringAgentThread"/>.
/// </summary>
public enum MessageStoringThreadStorageLocation
{
    /// <summary>
    /// The storage location is not yet known.
    /// </summary>
    /// <remarks>
    /// In some cases, whether a service supports storing messages in the agent service or not only becomes known
    /// during the first agent invocation. Therefore a thread may be in an <see cref="Unknown"/> state until the first
    /// invocation is complete.
    /// </remarks>
    Unknown = 0,

    /// <summary>
    /// Messages are stored externally in the <see cref="IChatMessageStore"/> of the thread.
    /// </summary>
    ChatMessageStore = 1,

    /// <summary>
    /// Messages are stored in the agent service and the thread object just has an id reference the service storage.
    /// </summary>
    AgentService = 2,
}
