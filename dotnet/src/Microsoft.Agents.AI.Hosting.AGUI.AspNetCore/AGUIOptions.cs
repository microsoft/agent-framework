// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Configuration options for AG-UI human-in-the-loop approval behavior.
/// </summary>
public sealed class AGUIOptions
{
    /// <summary>
    /// Gets or sets the timeout for pending tool approval requests.
    /// If the client does not POST to the /approve endpoint within this duration,
    /// the request is auto-denied. Default is 60 seconds.
    /// </summary>
    public TimeSpan ApprovalTimeout { get; set; } = TimeSpan.FromSeconds(60);
}
