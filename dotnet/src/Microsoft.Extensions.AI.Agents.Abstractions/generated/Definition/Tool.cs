// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
/// <summary>
/// /// Represents a tool that can be used in prompts..
/// </summary>
public sealed class Tool
{
    /// <summary>
    /// Initializes a new instance of <see cref="Tool"/>.
    /// </summary>
    public Tool()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Tool"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Tool(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Binding = props.GetValueOrDefault<IList<Binding>?>("binding");
    }

    /// <summary>
    /// The name of the item
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// The type identifier for the tool
    /// </summary>
    public string Type { get; set; } = string.Empty;

    /// <summary>
    /// A short description of the tool for metadata purposes
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Tool argument bindings to input properties
    /// </summary>
    public IList<Binding>? Binding { get; set; }
}
#pragma warning restore RCS1037 // Remove trailing white-space
