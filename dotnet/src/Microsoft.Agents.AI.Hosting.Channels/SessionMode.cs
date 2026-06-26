// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Controls how the host resolves an <see cref="AgentSession"/> for a <see cref="ChannelRequest"/>.
/// </summary>
public enum SessionMode
{
    /// <summary>Default. The host resolves a session if the channel supplies enough hints, otherwise runs ephemerally.</summary>
    Auto,

    /// <summary>The host MUST resolve or create a session; missing required hints surface as an error.</summary>
    Required,

    /// <summary>The host never resolves a session; the target runs ephemerally even if hints are present.</summary>
    Disabled,
}
