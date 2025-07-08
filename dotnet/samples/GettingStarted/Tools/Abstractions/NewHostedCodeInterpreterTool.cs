// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace GettingStarted.Tools.Abstractions;

/// <summary>
/// Proposal for abstraction updates based on the common code interpreter tool properties.
/// Based on the decision, the <see cref="HostedCodeInterpreterTool"/> abstraction can be updated in M.E.AI or specific SDK if some properties are not common.
/// </summary>
public class NewHostedCodeInterpreterTool : HostedCodeInterpreterTool
{
    public IList<string>? FileIds { get; set; }
}
