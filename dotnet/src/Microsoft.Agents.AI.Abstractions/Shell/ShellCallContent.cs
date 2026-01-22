// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a shell command execution request.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class ShellCallContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ShellCallContent"/> class.
    /// </summary>
    /// <param name="callId">The unique identifier for this shell call.</param>
    /// <param name="commands">The commands to execute.</param>
    [JsonConstructor]
    public ShellCallContent(string callId, IReadOnlyList<string> commands)
    {
        this.CallId = Throw.IfNull(callId);
        this.Commands = Throw.IfNull(commands);
    }

    /// <summary>
    /// Gets the unique identifier for this shell call.
    /// </summary>
    public string CallId { get; }

    /// <summary>
    /// Gets the commands to execute.
    /// </summary>
    public IReadOnlyList<string> Commands { get; }

    /// <summary>Gets a string representing this instance to display in the debugger.</summary>
    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        $"ShellCall = {this.CallId}, Commands = {this.Commands.Count}";
}
