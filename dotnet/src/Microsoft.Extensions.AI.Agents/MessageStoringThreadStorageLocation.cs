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
    Unknown = 0,

    /// <summary>
    /// Messages are managed by the <see cref="MessageStoringAgentThread"/> object.
    /// </summary>
    AgentThreadManaged = 1,

    /// <summary>
    /// Messages are stored in the agent service and the thread object just has an id reference the service storage.
    /// </summary>
    ConversationId = 2,
}
