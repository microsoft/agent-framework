// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Jobs;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Handler class for background job management.
/// </summary>
internal class ChannelHandler : IChannelHandler
{
    private readonly Channel<BackgroundJobBase> _jobChannel;
    private readonly List<Task> _channelListeners;
    private readonly ILogger _logger;
    private readonly PurviewSettings _purviewSettings;

    /// <summary>
    /// Creates a new instance of JobHandler.
    /// </summary>
    /// <param name="purviewSettings">The purview integration settings.</param>
    /// <param name="logger">The logger used for logging job information.</param>
    /// <param name="jobChannel">The job channel used for queuing and reading background jobs.</param>
    public ChannelHandler(PurviewSettings purviewSettings, ILogger logger, Channel<BackgroundJobBase> jobChannel)
    {
        this._purviewSettings = purviewSettings;
        this._logger = logger;
        this._jobChannel = jobChannel;

        this._channelListeners = new List<Task>(this._purviewSettings.MaxConcurrentJobConsumers);
    }

    /// <inheritdoc/>
    public void QueueJob(BackgroundJobBase job)
    {
        try
        {
            if (job == null)
            {
                throw new PurviewJobException("Cannot queue null job.");
            }

            if (this._channelListeners.Count == 0)
            {
                this._logger.LogWarning("No listeners are available to process the job.");
                throw new PurviewJobException("No listeners are available to process the job.");
            }

            bool canQueue = this._jobChannel.Writer.TryWrite(job);

            if (!canQueue)
            {
                int jobCount = this._jobChannel.Reader.Count;
                this._logger.LogError("Could not queue a job for background processing.");

                if (this._jobChannel.Reader.Completion.IsCompleted)
                {
                    throw new PurviewJobException("Job channel is closed or completed. Cannot queue job.");
                }
                else if (jobCount >= this._purviewSettings.PendingBackgroundJobLimit)
                {
                    throw new PurviewJobLimitExceededException($"Job queue is full. Current pending jobs: {jobCount}. Maximum number of queued jobs: {this._purviewSettings.PendingBackgroundJobLimit}");
                }
                else
                {
                    throw new PurviewJobException("Could not queue job for background processing.");
                }
            }
        }
        catch (Exception e) when (this._purviewSettings.IgnoreExceptions)
        {
            this._logger.LogError(e, "Error queuing job: {ExceptionMessage}", e.Message);
        }
    }

    /// <inheritdoc/>
    public void AddRunner(Func<Channel<BackgroundJobBase>, Task> runnerTask)
    {
        this._channelListeners.Add(Task.Run(async () => await runnerTask(this._jobChannel).ConfigureAwait(false)));
    }

    /// <inheritdoc/>
    public async Task StopAndWaitForCompletionAsync()
    {
        this._jobChannel.Writer.Complete();
        await this._jobChannel.Reader.Completion.ConfigureAwait(false);
        await Task.WhenAll(this._channelListeners).ConfigureAwait(false);
    }
}
