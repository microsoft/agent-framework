// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents;

/// <summary>
/// Defines the different supported storage locations for <see cref="ChatClientAgentThread"/>.
/// </summary>
public enum ChatClientAgentThreadStorageLocation
{
    /// <summary>
    /// Messages are stored in memory inside the thread object.
    /// </summary>
    LocalInMemory,

    /// <summary>
    /// Messages are stored in the service and the thread object just had an id reference the service storage.
    /// </summary>
    InService
}
