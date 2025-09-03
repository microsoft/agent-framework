// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
/// <summary>
/// Authentication configuration for the MCP tool
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class McpAuthentication
{
    /// <summary>
    /// Initializes a new instance of <see cref="McpAuthentication"/>.
    /// </summary>
    public McpAuthentication()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="McpAuthentication"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal McpAuthentication(IDictionary<string, object> props) : this()
    {
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Credentials = props.GetValueOrDefault<Options>("credentials") ?? throw new ArgumentException("Properties must contain a property named: credentials", nameof(props));
    }
    
    /// <summary>
    /// The type of authentication to use
    /// </summary>
    
    public string Type { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The credentials to use for authentication
    /// </summary>
    
    public Options Credentials { get; set; } = new Options();
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line

