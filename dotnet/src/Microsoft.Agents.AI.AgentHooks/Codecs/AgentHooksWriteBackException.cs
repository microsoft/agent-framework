// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// A transform verdict could not be converted back into the native framework value.
/// </summary>
/// <remarks>
/// Thrown (and deliberately never caught by this package) so an unappliable transform
/// fails the run closed instead of silently proceeding with the untransformed value.
/// </remarks>
internal sealed class AgentHooksWriteBackException : InvalidOperationException
{
    public AgentHooksWriteBackException()
    {
    }

    public AgentHooksWriteBackException(string message)
        : base(message)
    {
    }

    public AgentHooksWriteBackException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}
