// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Jobs;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Interface for a class that controls background job processing.
/// </summary>
internal interface IChannelHandler
{
    /// <summary>
    /// Queue a job for background processing.
    /// </summary>
    /// <param name="job">The job queued for background processing.</param>
    void QueueJob(BackgroundJobBase job);

    /// <summary>
    /// Add a runner to the channel handler.
    /// </summary>
    /// <param name="runnerTask">The runner task used to process jobs.</param>
    void AddRunner(Func<Channel<BackgroundJobBase>, Task> runnerTask);

    /// <summary>
    /// Stop the channel and wait for all runners to complete
    /// </summary>
    /// <returns>A task representing the job.</returns>
    Task StopAndWaitForCompletionAsync();
}
