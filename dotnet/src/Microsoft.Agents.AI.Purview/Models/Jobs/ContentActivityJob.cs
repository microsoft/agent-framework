// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Purview.Models.Requests;

namespace Microsoft.Agents.AI.Purview.Models.Jobs;
internal sealed class ContentActivityJob : BackgroundJobBase
{
    public ContentActivityJob(ContentActivitiesRequest request)
    {
        this.Request = request;
    }

    public ContentActivitiesRequest Request { get; }
}
