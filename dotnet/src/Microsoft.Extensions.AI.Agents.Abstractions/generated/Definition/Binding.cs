// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an instance of Binding.
/// </summary>
public sealed class Binding
{
    /// <summary>
    /// Initializes a new instance of <see cref="Binding"/>.
    /// </summary>
    public Binding()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Binding"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Binding(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Input = props.GetValueOrDefault<string>("input") ?? throw new ArgumentException("Properties must contain a property named: input", nameof(props));
    }

    /// <summary>
    /// The name of the item
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// The input property that will be bound to the tool parameter argument
    /// </summary>
    public string Input { get; set; } = string.Empty;
}
