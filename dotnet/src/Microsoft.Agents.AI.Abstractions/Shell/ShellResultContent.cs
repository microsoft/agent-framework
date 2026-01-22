// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the result of a shell command execution.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class ShellResultContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ShellResultContent"/> class.
    /// </summary>
    /// <param name="callId">The call ID matching the <see cref="ShellCallContent.CallId"/>.</param>
    /// <param name="output">The output for each command executed.</param>
    [JsonConstructor]
    public ShellResultContent(string callId, IReadOnlyList<ShellCommandOutput> output)
    {
        CallId = Throw.IfNull(callId);
        Output = Throw.IfNull(output);
    }

    /// <summary>
    /// Gets the call ID matching the <see cref="ShellCallContent.CallId"/>.
    /// </summary>
    public string CallId { get; }

    /// <summary>
    /// Gets the output for each command executed.
    /// </summary>
    public IReadOnlyList<ShellCommandOutput> Output { get; }

    /// <summary>
    /// Gets or sets the maximum output length that was applied.
    /// </summary>
    public int? MaxOutputLength { get; set; }

    /// <summary>Gets a string representing this instance to display in the debugger.</summary>
    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        $"ShellResult = {CallId}, Outputs = {Output.Count}";
}
