// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Azure.AI.Agents.Persistent;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
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

    protected Task<IChatClient> GetChatClientAsync(ChatClientProviders provider, ChatClientAgentOptions options, CancellationToken cancellationToken = default)
        => provider switch
        {
            ChatClientProviders.OpenAIChatCompletion => GetOpenAIChatClientAsync(),
            ChatClientProviders.OpenAIAssistant => GetOpenAIAssistantChatClientAsync(options, cancellationToken),
            ChatClientProviders.AzureOpenAI => GetAzureOpenAIChatClientAsync(),
            ChatClientProviders.AzureAIAgentsPersistent => GetAzureAIAgentPersistentClientAsync(options, cancellationToken),
            ChatClientProviders.OpenAIResponses or
            ChatClientProviders.OpenAIResponses_InMemoryMessageThread or
            ChatClientProviders.OpenAIResponses_ConversationIdThread
                => GetOpenAIResponsesClientAsync(),
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
    protected Task AgentCleanUpAsync(ChatClientProviders provider, ChatClientAgent agent, AgentThread? thread = null, CancellationToken cancellationToken = default)
    {
        return provider switch
        {
            ChatClientProviders.AzureAIAgentsPersistent => AzureAIAgentsPersistentAgentCleanUpAsync(agent, thread, cancellationToken),

            // For other remaining provider sample types, no cleanup is needed as they don't offer a server-side agent/thread clean-up API.
            _ => Task.CompletedTask
        };
    }

    #region Private GetChatClient

    private Task<IChatClient> GetOpenAIChatClientAsync()
        => Task.FromResult(
                new ChatClient(TestConfiguration.OpenAI.ChatModelId, TestConfiguration.OpenAI.ApiKey)
                    .AsIChatClient());

    private Task<IChatClient> GetAzureOpenAIChatClientAsync()
        => Task.FromResult(
            ((TestConfiguration.AzureOpenAI.ApiKey is null)
                // Use Azure CLI credentials if API key is not provided.
                ? new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new AzureCliCredential())
                : new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new ApiKeyCredential(TestConfiguration.AzureOpenAI.ApiKey)))
                    .GetChatClient(TestConfiguration.AzureOpenAI.DeploymentName)
                    .AsIChatClient());

    private Task<IChatClient> GetOpenAIResponsesClientAsync()
        => Task.FromResult(
                new OpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId, TestConfiguration.OpenAI.ApiKey)
                    .AsIChatClient());

    private async Task<IChatClient> GetAzureAIAgentPersistentClientAsync(ChatClientAgentOptions options, CancellationToken cancellationToken)
    {
        var persistentAgentsClient = new PersistentAgentsClient(
            TestConfiguration.AzureAI.Endpoint,
            new AzureCliCredential());

        // If the Id is not provided, create a new agent.
        if (options.Id is null)
        {
            var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
                       model: TestConfiguration.AzureAI.DeploymentName,
                       name: options.Name,
                       instructions: options.Instructions,
                       cancellationToken: cancellationToken);

            var persistentAgent = persistentAgentResponse.Value;

            return persistentAgentsClient.AsIChatClient(persistentAgent.Id);
        }

        return persistentAgentsClient.AsIChatClient(options.Id);
    }

    private async Task<IChatClient> GetOpenAIAssistantChatClientAsync(ChatClientAgentOptions options, CancellationToken cancellationToken)
    {
        var assistantClient = new AssistantClient(TestConfiguration.OpenAI.ApiKey);

        // If the Id is not provided, create a new assistant.
        if (options.Id is null)
        {
            Assistant assistant = await assistantClient.CreateAssistantAsync(
                TestConfiguration.OpenAI.ChatModelId,
                new()
                {
                    Name = options.Name,
                    Instructions = options.Instructions
                },
                cancellationToken);

            return new NewOpenAIAssistantChatClient(assistantClient, assistant.Id, null);
        }

        return new NewOpenAIAssistantChatClient(assistantClient, options.Id, null);
    }

    #endregion

    #region Private AgentCleanUp

    private async Task AzureAIAgentsPersistentAgentCleanUpAsync(ChatClientAgent agent, AgentThread? thread, CancellationToken cancellationToken)
    {
        var persistentAgentsClient = agent.ChatClient.GetService<PersistentAgentsClient>();
        if (persistentAgentsClient is null)
        {
            throw new InvalidOperationException("The provided chat client is not a Persistent Agents Chat Client");
        }

        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id, cancellationToken);

        // If a thread is provided, delete it as well.
        if (thread is not null)
        {
            await persistentAgentsClient.Threads.DeleteThreadAsync(thread.Id, cancellationToken);
        }
    }

    #endregion
}
