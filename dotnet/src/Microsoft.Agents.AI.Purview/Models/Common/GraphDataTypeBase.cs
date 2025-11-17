// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Base class for all graph data types used in the Purview SDK.
/// </summary>
internal abstract class GraphDataTypeBase
{
    /// <summary>
    /// Create a new instance of the <see cref="GraphDataTypeBase"/> class.
    /// </summary>
    /// <param name="dataType">The data type of the graph object.</param>
    public GraphDataTypeBase(string dataType)
    {
        this.DataType = dataType;
    }

    /// <summary>
    /// The @odata.type property name used in the JSON representation of the object.
    /// </summary>
    [JsonPropertyName(Constants.ODataTypePropertyName)]
    public string DataType { get; set; }
}
