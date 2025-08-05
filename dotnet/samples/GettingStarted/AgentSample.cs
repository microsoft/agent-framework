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

    protected IChatClient GetChatClient(ChatClientProviders provider, ChatClientAgentOptions? options = null)
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

    protected ChatOptions? GetChatOptions(ChatClientProviders? provider)
        => provider switch
        {
            ChatClientProviders.OpenAIResponses_InMemoryMessageThread => new() { RawRepresentationFactory = static (_) => new ResponseCreationOptions() { StoredOutputEnabled = false } },
            ChatClientProviders.OpenAIResponses_ConversationIdThread => new() { RawRepresentationFactory = static (_) => new ResponseCreationOptions() { StoredOutputEnabled = true } },
            _ => null
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
    protected Task AgentCleanUpAsync(ChatClientProviders provider, AIAgent agent, AgentThread? thread = null, CancellationToken cancellationToken = default)
    {
        return provider switch
        {
            ChatClientProviders.AzureAIAgentsPersistent => AzureAIAgentsPersistentAgentCleanUpAsync(agent, thread, cancellationToken),
            ChatClientProviders.OpenAIAssistant => OpenAIAssistantCleanUpAgentAsync(agent, thread, cancellationToken),
            // For other remaining provider sample types, no cleanup is needed as they don't offer a server-side agent/thread clean-up API.
            _ => Task.CompletedTask
        };
    }

    /// <summary>
    /// Creates a server-side agent identifier based on the specified provider and options.
    /// </summary>
    /// <param name="provider">The provider to use for creating the agent.</param>
    /// <param name="options">The options to configure the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The identifier of the created agent, or <see langword="null"/> if the provider does not use server-side agents.</returns>
    /// <remarks>Some server-side agent providers require an agent id reference to be created before it can be invoked.</remarks>
    protected Task<string?> AgentCreateAsync(ChatClientProviders provider, ChatClientAgentOptions options, CancellationToken cancellationToken = default)
    {
        return provider switch
        {
            ChatClientProviders.OpenAIAssistant => OpenAIAssistantCreateAgentAsync(options, cancellationToken),
            ChatClientProviders.AzureAIAgentsPersistent => AzureAIAgentsPersistentCreateAgentAsync(options, cancellationToken),
            _ => Task.FromResult<string?>(null)
        };
    }

    #region Private GetChatClient

    private IChatClient GetOpenAIChatClient()
        => new ChatClient(TestConfiguration.OpenAI.ChatModelId, TestConfiguration.OpenAI.ApiKey)
            .AsIChatClient();

    private IChatClient GetAzureOpenAIChatClient()
        => ((TestConfiguration.AzureOpenAI.ApiKey is null)
            // Use Azure CLI credentials if API key is not provided.
            ? new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new AzureCliCredential())
            : new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new ApiKeyCredential(TestConfiguration.AzureOpenAI.ApiKey)))
                .GetChatClient(TestConfiguration.AzureOpenAI.DeploymentName)
                .AsIChatClient();

    private IChatClient GetOpenAIResponsesClient()
        => new OpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId, TestConfiguration.OpenAI.ApiKey)
            .AsIChatClient();

    private NewPersistentAgentsChatClient GetAzureAIAgentPersistentClient(ChatClientAgentOptions options)
        => new(new PersistentAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential()), options.Id!);

    private NewOpenAIAssistantChatClient GetOpenAIAssistantChatClient(ChatClientAgentOptions options)
        => new(new(TestConfiguration.OpenAI.ApiKey), options.Id!, null);

    #endregion

    #region Private AgentCreate

    private async Task<string?> AzureAIAgentsPersistentCreateAgentAsync(ChatClientAgentOptions options, CancellationToken cancellationToken)
    {
        var persistentAgentsClient = new Azure.AI.Agents.Persistent.PersistentAgentsAdministrationClient(
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

    private async Task<string?> OpenAIAssistantCreateAgentAsync(ChatClientAgentOptions options, CancellationToken cancellationToken)
    {
        var assistantClient = new OpenAI.Assistants.AssistantClient(TestConfiguration.OpenAI.ApiKey);
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

    private async Task AzureAIAgentsPersistentAgentCleanUpAsync(AIAgent agent, AgentThread? thread, CancellationToken cancellationToken)
    {
        var persistentAgentsClient = (agent as ChatClientAgent)?.ChatClient.GetService<PersistentAgentsClient>() ??
            throw new InvalidOperationException("The provided chat client is not a Persistent Agents Chat Client");

        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id, cancellationToken);

        // If a thread is provided, delete it as well.
        if (thread is not null)
        {
            await persistentAgentsClient.Threads.DeleteThreadAsync(thread.ConversationId, cancellationToken);
        }
    }

    private async Task OpenAIAssistantCleanUpAgentAsync(AIAgent agent, AgentThread? thread, CancellationToken cancellationToken)
    {
        var assistantClient = (agent as ChatClientAgent)?.ChatClient
            .GetService<AssistantClient>()
            ?? throw new InvalidOperationException("The provided chat client is not an OpenAI Assistant Chat Client");

        // Delete the agent.
        await assistantClient.DeleteAssistantAsync(agent.Id, cancellationToken);

        // If a thread is provided, delete it as well.
        if (thread is not null)
        {
            await assistantClient.DeleteThreadAsync(thread.ConversationId, cancellationToken);
        }
    }

    #endregion
}
