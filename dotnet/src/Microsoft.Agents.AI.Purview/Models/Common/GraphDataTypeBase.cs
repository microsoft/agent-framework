// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Base class for all graph data types used in the Purview SDK.
/// </summary>
internal abstract class GraphDataTypeBase
{
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
