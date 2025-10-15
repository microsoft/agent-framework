// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI.Agents.Purview.Models.Common;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Extensions.AI.Agents.Purview;

/// <summary>
/// A delegating agent that connects to Microsoft Purview.
/// </summary>
public sealed class PurviewAgentWrapper
{
    private readonly ILogger _logger;
    private readonly ScopedContentProcessor _scopedProcessor;
    private readonly PurviewSettings _purviewSettings;

    /// <summary>
    /// Creates a new <see cref="PurviewAgentWrapper"/> instance.
    /// </summary>
    /// <param name="tokenCredential"></param>
    /// <param name="purviewSettings"></param>
    /// <param name="logger"></param>
    public PurviewAgentWrapper(TokenCredential tokenCredential, PurviewSettings purviewSettings, ILogger? logger = null)
    {
        this._logger = logger ?? NullLogger.Instance;
        this._scopedProcessor = new ScopedContentProcessor(new PurviewClient(tokenCredential, purviewSettings));
        this._purviewSettings = purviewSettings;
    }

    /// <inheritdoc />
    public async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
    {
        bool shouldBlockPrompt = await this._scopedProcessor.ProcessMessagesAsync(messages, thread, Activity.UploadText, this._purviewSettings, cancellationToken).ConfigureAwait(false);

        if (shouldBlockPrompt)
        {
            this._logger.LogInformation("Prompt blocked by policy");
            return new AgentRunResponse(new ChatMessage(ChatRole.System, "Prompt blocked by policy"));
        }

        var response = await innerAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

        bool shouldBlockResponse = await this._scopedProcessor.ProcessMessagesAsync(response.Messages, thread, Activity.UploadText, this._purviewSettings, cancellationToken).ConfigureAwait(false);

        if (shouldBlockResponse)
        {
            this._logger.LogInformation("Response blocked by policy");
            return new AgentRunResponse(new ChatMessage(ChatRole.System, "Response blocked by policy"));
        }

        return response;
    }
}
