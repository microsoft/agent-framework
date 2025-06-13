// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents;

/// <summary>
/// Defines the different supported storage locations for <see cref="ChatClientAgentThread"/>.
/// </summary>
internal enum ChatClientAgentThreadType
{
    /// <summary>
    /// Messages are stored by the thread object in the location of its choice.
    /// </summary>
    AgentThreadManaged,

    /// <summary>
    /// Messages are stored in the agent service and the thread object just has an id reference to the service storage.
    /// </summary>
    ConversationId
}
