// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Assistants;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="AIAgent"/> using a <see cref="AssistantClient"/>.
/// </summary>
public sealed class OpenAIAssistantAgentFactory : OpenAIAgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIChatAgentFactory"/> class.
    /// </summary>
    public OpenAIAssistantAgentFactory(IList<AIFunction>? functions = null, ILoggerFactory? loggerFactory = null) : base(loggerFactory)
    {
        this._functions = functions;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIChatAgentFactory"/> class.
    /// </summary>
    public OpenAIAssistantAgentFactory(AssistantClient assistantClient, IList<AIFunction>? functions = null, ILoggerFactory? loggerFactory = null) : base(loggerFactory)
    {
        Throw.IfNull(assistantClient);

        this._assistantClient = assistantClient;
        this._functions = functions;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIChatAgentFactory"/> class.
    /// </summary>
    public OpenAIAssistantAgentFactory(Uri endpoint, TokenCredential tokenCredential, IList<AIFunction>? functions = null, ILoggerFactory? loggerFactory = null) : base(endpoint, tokenCredential, loggerFactory)
    {
        this._functions = functions;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var apiType = promptAgent.Model.ApiType;
        if (apiType?.IsUnknown() == true && apiType.UnknownValue?.Equals(API_TYPE_ASSISTANTS, StringComparison.OrdinalIgnoreCase) == true)
        {
            return null;
        }

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            Instructions = promptAgent.Instructions?.ToTemplateString(),
            ChatOptions = promptAgent.GetChatOptions(this._functions),
        };

        AssistantClient? assistantClient = this._assistantClient ?? this.CreateAssistantClient(promptAgent);
        if (assistantClient is not null)
        {
            var modelId = promptAgent.Model?.Id?.LiteralValue;
            Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI Assistant.");
            Throw.IfNullOrEmpty(promptAgent.Instructions?.ToTemplateString(), "The instructions must be specified in the agent definition to create an OpenAI Assistant.");

            return await assistantClient.CreateAIAgentAsync(
                modelId,
                options
            ).ConfigureAwait(false);
        }

        return null;
    }

    #region private
    private readonly AssistantClient? _assistantClient;
    private readonly IList<AIFunction>? _functions;

    private const string API_TYPE_ASSISTANTS = "ASSISTANTS";
    #endregion
}
