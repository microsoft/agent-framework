// Copyright (c) Microsoft. All rights reserved.
using System.ClientModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.A2A;
using Microsoft.Extensions.Logging;
using OpenAI;

namespace A2A;

internal sealed class HostClientAgent
{
    internal HostClientAgent(ILoggerFactory loggerFactory)
    {
        this._logger = loggerFactory.CreateLogger("HostClientAgent");
    }

    internal async Task InitializeAgentAsync(string modelId, string apiKey, string[] agentUrls)
    {
        try
        {
            this._logger.LogInformation("Initializing Agent Framework agent with model: {ModelId}", modelId);

            // Connect to the remote agents via A2A
            var createAgentTasks = agentUrls.Select(CreateAgentAsync);
            var agents = await Task.WhenAll(createAgentTasks);
            var tools = agents.Select(agent => (AITool)agent.AsAIFunction()).ToList();

            // Create the agent that uses the remote agents as tools
            this.Agent = new OpenAIClient(new ApiKeyCredential(apiKey))
             .GetChatClient(modelId)
             .CreateAIAgent(instructions: "You specialize in handling queries for users and using your tools to provide answers.", name: "HostClient", tools: tools);
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Failed to initialize HostClientAgent");
            throw;
        }
    }

    /// <summary>
    /// The associated <see cref="Agent"/>
    /// </summary>
    public AIAgent? Agent { get; private set; }

    #region private
    private readonly ILogger _logger;

    private static async Task<AIAgent> CreateAgentAsync(string agentUri)
    {
        var url = new Uri(agentUri);
        var httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(60)
        };

        var agentCardResolver = new A2ACardResolver(url, httpClient);

        return await agentCardResolver.GetAIAgentAsync();
    }
    #endregion
}
