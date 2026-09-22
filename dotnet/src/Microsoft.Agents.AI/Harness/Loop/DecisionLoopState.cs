// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// The default, minimal state projection that <see cref="DecisionLoopEvaluator"/> sends to its decision source.
/// </summary>
internal sealed class DecisionLoopState
{
    /// <summary>Gets or sets the text projection of the original request messages.</summary>
    public IList<DecisionLoopMessage> OriginalRequest { get; set; } = [];

    /// <summary>Gets or sets the text of the agent's latest response.</summary>
    public string LatestResponse { get; set; } = string.Empty;

    /// <summary>Gets or sets the number of completed iterations.</summary>
    public int Iteration { get; set; }
}

/// <summary>
/// The text projection of a single original request message in <see cref="DecisionLoopState"/>.
/// </summary>
internal sealed class DecisionLoopMessage
{
    /// <summary>Gets or sets the message role.</summary>
    public string Role { get; set; } = string.Empty;

    /// <summary>Gets or sets the message text.</summary>
    public string Text { get; set; } = string.Empty;
}
