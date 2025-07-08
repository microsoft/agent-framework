// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Defines the different supported storage locations for <see cref="ChatClientAgentThread"/>.
/// </summary>
internal enum ChatClientAgentThreadType
{
    /// <summary>
    /// Messages are stored in memory inside the thread object.
    /// </summary>
    InMemoryMessages,

    /// <summary>
    /// Messages are stored in the service and the thread object just has an id reference the service storage.
    /// </summary>
    ConversationId
}
