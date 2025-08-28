// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an instance of Output.
/// </summary>
public sealed class Output
{
    /// <summary>
    /// Initializes a new instance of <see cref="Output"/>.
    /// </summary>
    public Output()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Output"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Output(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Required = props.GetValueOrDefault<bool?>("required");
    }

    /// <summary>
    /// The name of the item
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// The data type of the output property
    /// </summary>
    public string Type { get; set; } = string.Empty;

    /// <summary>
    /// A short description of the output property
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Whether the output property is required
    /// </summary>
    public bool? Required { get; set; }
}
