// Copyright (c) Microsoft. All rights reserved.

// Line removed as it is unnecessary due to ImplicitUsings being enabled.

using System.Collections.Generic;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Proposal for abstraction updates based on the common file search tool properties.
/// This provides a standardized interface for file search functionality across providers.
/// </summary>
public class NewHostedFileSearchTool : AITool
{
    /// <summary>Gets or sets a collection of <see cref="AIContent"/> to be used as input to the code interpreter tool.</summary>
    /// <remarks>
    /// Services support different varied kinds of inputs. Most support the IDs of vector stores that are hosted by the service,
    /// represented via <see cref="HostedVectorStoreContent"/>. Some also support binary data, represented via <see cref="DataContent"/>.
    /// Unsupported inputs will be ignored by the <see cref="IChatClient"/> to which the tool is passed.
    /// </remarks>
    public IList<AIContent>? Inputs { get; set; }
}
