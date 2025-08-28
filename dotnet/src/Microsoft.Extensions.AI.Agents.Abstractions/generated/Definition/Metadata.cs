// Copyright (c) Microsoft. All rights reserved.
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an instance of Metadata.
/// </summary>
public sealed class Metadata
{
    /// <summary>
    /// Initializes a new instance of <see cref="Metadata"/>.
    /// </summary>
    public Metadata()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Metadata"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Metadata(IDictionary<string, object> props) : this()
    {
    }
}
