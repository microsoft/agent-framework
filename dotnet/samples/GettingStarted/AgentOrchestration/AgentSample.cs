// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Azure.AI.Agents.Persistent;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;
using Microsoft.Shared.Samples;
using OpenAI.Assistants;
using OpenAI.Chat;
using OpenAI.Responses;

#pragma warning disable OPENAI001

namespace GettingStarted;

public class AgentSample(ITestOutputHelper output) : BaseSample(output)
{
    /// <summary>
    /// Represents the available providers for <see cref="IChatClient"/> instances.
    /// </summary>
    public enum ChatClientProviders
    {
        AzureOpenAI,
        OpenAIChatCompletion,
        OpenAIAssistant,
        OpenAIResponses,
        OpenAIResponses_InMemoryMessageThread,
        OpenAIResponses_ConversationIdThread,
        AzureAIAgentsPersistent
    }

    protected static IChatClient GetChatClient(ChatClientProviders provider, ChatClientAgentOptions? options = null)
        => provider switch
        {
            ChatClientProviders.OpenAIChatCompletion => GetOpenAIChatClient(),
            ChatClientProviders.OpenAIAssistant => GetOpenAIAssistantChatClient(Throw.IfNull(options)),
            ChatClientProviders.AzureOpenAI => GetAzureOpenAIChatClient(),
            ChatClientProviders.AzureAIAgentsPersistent => GetAzureAIAgentPersistentClient(Throw.IfNull(options)),
            ChatClientProviders.OpenAIResponses or
            ChatClientProviders.OpenAIResponses_InMemoryMessageThread or
            ChatClientProviders.OpenAIResponses_ConversationIdThread
                => GetOpenAIResponsesClient(),
            _ => throw new NotSupportedException($"Provider {provider} is not supported.")
        };

    /// <summary>
    /// For providers that store the agent and the thread on the server side, this will clean and delete
    /// any sample agent and thread that was created during this execution.
    /// </summary>
    /// <param name="provider">The chat client provider type that determines the cleanup process.</param>
    /// <param name="agent">The agent instance to be cleaned up.</param>
    /// <param name="thread">Optional thread associated with the agent that may also need to be cleaned up.</param>
    /// <param name="cancellationToken">Cancellation token to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <remarks>
    /// Ideally for faster execution and potential cost savings, server-side agents should be reused.
    /// </remarks>
    protected static Task AgentCleanUpAsync(ChatClientProviders provider, AIAgent agent, AgentThread? thread = null, CancellationToken cancellationToken = default)
        => provider switch
        {
            ChatClientProviders.AzureAIAgentsPersistent => AzureAIAgentsPersistentAgentCleanUpAsync(agent, thread, cancellationToken),
            ChatClientProviders.OpenAIAssistant => OpenAIAssistantCleanUpAgentAsync(agent, thread, cancellationToken),
            // For other remaining provider sample types, no cleanup is needed as they don't offer a server-side agent/thread clean-up API.
            _ => Task.CompletedTask
        };

    /// <summary>
    /// Creates a server-side agent identifier based on the specified provider and options.
    /// </summary>
    /// <param name="provider">The provider to use for creating the agent.</param>
    /// <param name="options">The options to configure the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The identifier of the created agent, or <see langword="null"/> if the provider does not use server-side agents.</returns>
    /// <remarks>Some server-side agent providers require an agent id reference to be created before it can be invoked.</remarks>
    protected static Task<string?> AgentCreateAsync(ChatClientProviders provider, ChatClientAgentOptions options, CancellationToken cancellationToken = default)
        => provider switch
        {
            ChatClientProviders.OpenAIAssistant => OpenAIAssistantCreateAgentAsync(options, cancellationToken),
            ChatClientProviders.AzureAIAgentsPersistent => AzureAIAgentsPersistentCreateAgentAsync(options, cancellationToken),
            _ => Task.FromResult<string?>(null)
        };

    #region Private GetChatClient

    private static IChatClient GetOpenAIChatClient()
        => new ChatClient(TestConfiguration.OpenAI.ChatModelId, TestConfiguration.OpenAI.ApiKey)
            .AsIChatClient();

    private static IChatClient GetAzureOpenAIChatClient()
        => ((TestConfiguration.AzureOpenAI.ApiKey is null)
            // Use Azure CLI credentials if API key is not provided.
            ? new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new AzureCliCredential())
            : new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new ApiKeyCredential(TestConfiguration.AzureOpenAI.ApiKey)))
                .GetChatClient(TestConfiguration.AzureOpenAI.DeploymentName)
                .AsIChatClient();

    private static IChatClient GetOpenAIResponsesClient()
        => new OpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId, TestConfiguration.OpenAI.ApiKey)
        .AsIChatClient();

    private static IChatClient GetAzureAIAgentPersistentClient(ChatClientAgentOptions options)
        => new PersistentAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential()).AsNewIChatClient(options.Id!);

    private static IChatClient GetOpenAIAssistantChatClient(ChatClientAgentOptions options)
        => new AssistantClient(TestConfiguration.OpenAI.ApiKey).AsIChatClient(options.Id!);

    #endregion

    #region Private AgentCreate

    private static async Task<string?> AzureAIAgentsPersistentCreateAgentAsync(ChatClientAgentOptions options, CancellationToken cancellationToken)
    {
        var persistentAgentsClient = new PersistentAgentsAdministrationClient(
            TestConfiguration.AzureAI.Endpoint,
            new AzureCliCredential());

        // Create a server side agent to work with.
        var result = await persistentAgentsClient.CreateAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName,
            name: options.Name,
            instructions: options.Instructions,
            cancellationToken: cancellationToken);

        return result?.Value.Id;
    }

    private static async Task<string?> OpenAIAssistantCreateAgentAsync(ChatClientAgentOptions options, CancellationToken cancellationToken)
    {
        var assistantClient = new AssistantClient(TestConfiguration.OpenAI.ApiKey);
        Assistant assistant = await assistantClient.CreateAssistantAsync(
            TestConfiguration.OpenAI.ChatModelId,
            new()
            {
                Name = options.Name,
                Instructions = options.Instructions
            },
            cancellationToken);

        return assistant.Id;
    }

    #endregion

    #region Private AgentCleanUp

    private static async Task AzureAIAgentsPersistentAgentCleanUpAsync(AIAgent agent, AgentThread? thread, CancellationToken cancellationToken)
    {
        var persistentAgentsClient = (agent as ChatClientAgent)?.ChatClient.GetService<PersistentAgentsClient>() ??
            throw new InvalidOperationException("The provided chat client is not a Persistent Agents Chat Client");

        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id, cancellationToken);

        // If a thread is provided, delete it as well.
        if (thread is ChatClientAgentThread chatThread)
        {
            await persistentAgentsClient.Threads.DeleteThreadAsync(chatThread.ConversationId, cancellationToken);
        }
    }

    private static async Task OpenAIAssistantCleanUpAgentAsync(AIAgent agent, AgentThread? thread, CancellationToken cancellationToken)
    {
        var assistantClient = (agent as ChatClientAgent)?.ChatClient
            .GetService<AssistantClient>()
            ?? throw new InvalidOperationException("The provided chat client is not an OpenAI Assistant Chat Client");

        // Delete the agent.
        await assistantClient.DeleteAssistantAsync(agent.Id, cancellationToken);

        // If a thread is provided, delete it as well.
        if (thread is ChatClientAgentThread chatThread)
        {
            await assistantClient.DeleteThreadAsync(chatThread.ConversationId, cancellationToken);
        }
    }

    #endregion
}
