// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an instance of Input.
/// </summary>
public sealed class Input
{
    /// <summary>
    /// Initializes a new instance of <see cref="Input"/>.
    /// </summary>
    public Input()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Input"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Input(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Required = props.GetValueOrDefault<bool?>("required");
        Strict = props.GetValueOrDefault<bool?>("strict");
        Default = props.GetValueOrDefault<object?>("default");
        Sample = props.GetValueOrDefault<object?>("sample");
    }

    /// <summary>
    /// The name of the item
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// The data type of the input property
    /// </summary>
    public string Type { get; set; } = string.Empty;

    /// <summary>
    /// A short description of the input property
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Whether the input property is required
    /// </summary>
    public bool? Required { get; set; }

    /// <summary>
    /// Whether the input property can emit structural text when parsing output
    /// </summary>
    public bool? Strict { get; set; }

    /// <summary>
    /// The default value of the input
    /// </summary>
    public object? Default { get; set; }

    /// <summary>
    /// A sample value of the input for examples and tooling
    /// </summary>
    public object? Sample { get; set; }
}
