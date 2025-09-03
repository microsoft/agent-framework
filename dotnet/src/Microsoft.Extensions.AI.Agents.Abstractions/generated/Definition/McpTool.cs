// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// The MCP Server tool.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class McpTool : Tool
{
    /// <summary>
    /// Initializes a new instance of <see cref="McpTool"/>.
    /// </summary>
    public McpTool()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="McpTool"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal McpTool(IDictionary<string, object> props) : this()
    {
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Options = props.GetValueOrDefault<McpToolOptions>("options") ?? throw new ArgumentException("Properties must contain a property named: options", nameof(props));
    }
    
    /// <summary>
    /// The type identifier for MCP tools
    /// </summary>
    
    public override string Type { get; set; } = "mcp";
    
    
    /// <summary>
    /// The options for the MCP tool
    /// </summary>
    
    public McpToolOptions Options { get; set; } = new McpToolOptions();
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

