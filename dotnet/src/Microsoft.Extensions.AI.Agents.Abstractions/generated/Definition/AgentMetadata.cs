// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
/// <summary>
/// /// Metadata model that can be used to store additional information about the model.
/// This can include arbitrary key-value pairs that provide context or configuration
/// for the model's behavior or usage.
/// 
/// Example:
/// ```yaml
/// metadata:
///   organization: Example Corp
///   authors:
///     - name: John Doe
///       email: john.doe@example.com
///       affiliation: Example Corp
///   tags:
///     - tag1
///     - tag2
///     - tag3
/// ```.
/// </summary>
public sealed class AgentMetadata
{
    /// <summary>
    /// Initializes a new instance of <see cref="AgentMetadata"/>.
    /// </summary>
    public AgentMetadata()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="AgentMetadata"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal AgentMetadata(IDictionary<string, object> props) : this()
    {
    }
}
#pragma warning restore RCS1037 // Remove trailing white-space
