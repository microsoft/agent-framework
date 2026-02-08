// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Purview.Models.Requests;

namespace Microsoft.Agents.AI.Purview.Models.Jobs;

/// <summary>
/// Class representing a job to send content activities to the Purview service.
/// </summary>
internal sealed class ContentActivityJob : BackgroundJobBase
{
    /// <summary>
    /// Create a new instance of the <see cref="ContentActivityJob"/> class.
    /// </summary>
    /// <param name="request">The content activities request to be sent in the background.</param>
    public ContentActivityJob(ContentActivitiesRequest request)
    {
        this.Request = request;
    }

    /// <summary>
    /// The request to send to the Purview service.
    /// </summary>
    public ContentActivitiesRequest Request { get; }
}
