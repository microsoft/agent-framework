// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Purview.Models.Common;

namespace Microsoft.Agents.AI.Purview.Models.Responses;

/// <summary>
/// Represents the response for content activities requests.
/// </summary>
internal sealed class ContentActivitiesResponse
{
    /// <summary>
    /// Gets or sets the HTTP status code associated with the response.
    /// </summary>
    [JsonIgnore]
    public HttpStatusCode StatusCode { get; set; }

    /// <summary>
    /// Details about any errors returned by the request.
    /// </summary>
    [JsonPropertyName("error")]
    public ErrorDetails? Error { get; set; }
}
