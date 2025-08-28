// Copyright (c) Microsoft. All rights reserved.
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an instance of Options.
/// </summary>
public sealed class Options
{
    /// <summary>
    /// Initializes a new instance of <see cref="Options"/>.
    /// </summary>
    public Options()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Options"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Options(IDictionary<string, object> props) : this()
    {
    }
}
