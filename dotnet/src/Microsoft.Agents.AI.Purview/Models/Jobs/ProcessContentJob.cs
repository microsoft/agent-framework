// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Purview.Models.Requests;

namespace Microsoft.Agents.AI.Purview.Models.Jobs;

/// <summary>
/// Class representing a job to process content.
/// </summary>
internal sealed class ProcessContentJob : BackgroundJobBase
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ProcessContentJob"/> class.
    /// </summary>
    /// <param name="request">The process content request to be sent in the background.</param>
    public ProcessContentJob(ProcessContentRequest request)
    {
        this.Request = request;
    }

    /// <summary>
    /// The request to process content.
    /// </summary>
    public ProcessContentRequest Request { get; }
}
