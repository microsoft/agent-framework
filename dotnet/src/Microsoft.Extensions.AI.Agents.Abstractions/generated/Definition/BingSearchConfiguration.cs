// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Configuration options for the Bing search tool.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class BingSearchConfiguration
{
    /// <summary>
    /// Initializes a new instance of <see cref="BingSearchConfiguration"/>.
    /// </summary>
    public BingSearchConfiguration()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="BingSearchConfiguration"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal BingSearchConfiguration(IDictionary<string, object> props) : this()
    {
        ConnectionId = props.GetValueOrDefault<string>("connectionId") ?? throw new ArgumentException("Properties must contain a property named: connectionId", nameof(props));
        InstanceName = props.GetValueOrDefault<string>("instanceName") ?? throw new ArgumentException("Properties must contain a property named: instanceName", nameof(props));
        Market = props.GetValueOrDefault<string?>("market");
        SetLang = props.GetValueOrDefault<string?>("setLang");
        Count = props.GetValueOrDefault<object?>("count");
        Freshness = props.GetValueOrDefault<string?>("freshness");
    }
    
    /// <summary>
    /// Connection id for grounding with bing search
    /// </summary>
    
    public string ConnectionId { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The instance name of the Bing search tool, used to identify the specific instance in the system
    /// </summary>
    
    public string InstanceName { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The market where the results come from.
    /// </summary>
    
    public string? Market { get; set; }
    
    
    /// <summary>
    /// The language to use for user interface strings when calling Bing API.
    /// </summary>
    
    public string? SetLang { get; set; }
    
    
    /// <summary>
    /// The number of search results to return in the bing api response
    /// </summary>
    
    public object? Count { get; set; }
    
    
    /// <summary>
    /// Filter search results by a specific time range. Accepted values: https://learn.microsoft.com/bing/search-apis/bing-web-search/reference/query-parameters
    /// </summary>
    
    public string? Freshness { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

