// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Purview.Models.Requests;

namespace Microsoft.Agents.AI.Purview.Models.Jobs;
internal sealed class ProcessContentJob : BackgroundJobBase
{
    public ProcessContentJob(ProcessContentRequest request)
    {
        this.Request = request;
    }

    public ProcessContentRequest Request { get; }
}
