// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Jobs;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Interface for a class that controlls background job processing.
/// </summary>
internal interface IChannelHandler
{
    /// <summary>
    /// Queue a job for background processing.
    /// </summary>
    /// <param name="job"></param>
    void QueueJob(BackgroundJobBase job);

    /// <summary>
    /// Add a runner to the channel handler.
    /// </summary>
    /// <param name="runnerTask"></param>
    void AddRunner(Func<Channel<BackgroundJobBase>, Task> runnerTask);

    /// <summary>
    /// Stop the channel and wait for all runners to complete
    /// </summary>
    /// <returns></returns>
    Task StopAndWaitForCompletionAsync();
}
