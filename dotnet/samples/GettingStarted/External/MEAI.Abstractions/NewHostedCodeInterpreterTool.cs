// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI;

/// <summary>
/// Proposal for abstraction updates based on the common code interpreter tool properties.
/// Based on the decision, the <see cref="HostedCodeInterpreterTool"/> abstraction can be updated in M.E.AI directly.
/// </summary>
public class NewHostedCodeInterpreterTool : HostedCodeInterpreterTool
{
    /// <summary>Gets or sets a collection of <see cref="AIContent"/> to be used as input to the code interpreter tool.</summary>
    /// <remarks>
    /// Services support different varied kinds of inputs. Most support the IDs of files that are hosted by the service,
    /// represented via <see cref="HostedFileContent"/>. Some also support binary data, represented via <see cref="DataContent"/>.
    /// Unsupported inputs will be ignored by the <see cref="IChatClient"/> to which the tool is passed.
    /// </remarks>
    public IList<AIContent>? Inputs { get; set; }
}
