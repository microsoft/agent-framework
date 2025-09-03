// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
/// <summary>
/// Configuration options for the MCP tool.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class McpToolOptions
{
    /// <summary>
    /// Initializes a new instance of <see cref="McpToolOptions"/>.
    /// </summary>
    public McpToolOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="McpToolOptions"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal McpToolOptions(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Url = props.GetValueOrDefault<string>("url") ?? throw new ArgumentException("Properties must contain a property named: url", nameof(props));
        Allowed = props.GetValueOrDefault<IList<string>>("allowed") ?? throw new ArgumentException("Properties must contain a property named: allowed", nameof(props));
        Authentication = props.GetValueOrDefault<McpAuthentication>("authentication") ?? throw new ArgumentException("Properties must contain a property named: authentication", nameof(props));
    }
    
    /// <summary>
    /// The name of the MCP tool
    /// </summary>
    
    public string Name { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The URL of the MCP server
    /// </summary>
    #pragma warning disable CA1056 // URI-like properties should not be strings
    public string Url { get; set; } = string.Empty;
    #pragma warning restore CA1056 // URI-like properties should not be strings
    
    /// <summary>
    /// List of allowed operations or resources for the MCP tool
    /// </summary>
    
    public IList<string> Allowed { get; set; } = [];
    
    
    /// <summary>
    /// Authentication configuration for the MCP tool
    /// </summary>
    
    public McpAuthentication Authentication { get; set; } = new McpAuthentication();
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line

