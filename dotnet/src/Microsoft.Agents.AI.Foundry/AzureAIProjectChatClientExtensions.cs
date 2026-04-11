// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace Azure.AI.Projects;

/// <summary>
/// Provides extension methods for <see cref="AIProjectClient"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static partial class AzureAIProjectChatClientExtensions
{
    /// <summary>
    /// Uses an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AIProjectClient"/> and <see cref="AgentReference"/>.
    /// </summary>
    /// <param name="aiProjectClient">The <see cref="AIProjectClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="agentReference">The <see cref="AgentReference"/> representing the name and version of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="agentReference"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    /// <remarks>
    /// When instantiating a <see cref="ChatClientAgent"/> by using an <see cref="AgentReference"/>, minimal information will be available about the agent in the instance level, and any logic that relies
    /// on <see cref="AIAgent.GetService{TService}(object?)"/> to retrieve information about the agent like <see cref="ProjectsAgentVersion" /> will receive <see langword="null"/> as the result.
    /// </remarks>
    public static FoundryAgent AsAIAgent(
        this AIProjectClient aiProjectClient,
        AgentReference agentReference,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentReference);
        ThrowIfInvalidAgentName(agentReference.Name);

        var innerAgent = AsChatClientAgent(
            aiProjectClient,
            agentReference,
            new ChatClientAgentOptions()
            {
                Id = $"{agentReference.Name}:{agentReference.Version}",
                Name = agentReference.Name,
                ChatOptions = new() { Tools = tools },
            },
            clientFactory,
            services);

        return new FoundryAgent(aiProjectClient, innerAgent);
    }

    /// <summary>
    /// Uses an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AIProjectClient"/> and <see cref="ProjectsAgentRecord"/>.
    /// </summary>
    /// <param name="aiProjectClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentRecord">The agent record to be converted. The latest version will be used. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="agentRecord"/> is <see langword="null"/>.</exception>
    public static FoundryAgent AsAIAgent(
        this AIProjectClient aiProjectClient,
        ProjectsAgentRecord agentRecord,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentRecord);

        var allowDeclarativeMode = tools is not { Count: > 0 };

        var innerAgent = AsChatClientAgent(
            aiProjectClient,
            agentRecord,
            tools,
            clientFactory,
            !allowDeclarativeMode,
            services);

        return new FoundryAgent(aiProjectClient, innerAgent);
    }

    /// <summary>
    /// Uses an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AIProjectClient"/> and <see cref="ProjectsAgentVersion"/>.
    /// </summary>
    /// <param name="aiProjectClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentVersion">The agent version to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">In-process invocable tools to be provided. If no tools are provided manual handling will be necessary to invoke in-process tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the provided version of the Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="agentVersion"/> is <see langword="null"/>.</exception>
    public static FoundryAgent AsAIAgent(
        this AIProjectClient aiProjectClient,
        ProjectsAgentVersion agentVersion,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentVersion);

        var allowDeclarativeMode = tools is not { Count: > 0 };

        var innerAgent = AsChatClientAgent(
            aiProjectClient,
            agentVersion,
            tools,
            clientFactory,
            !allowDeclarativeMode,
            services);

        return new FoundryAgent(aiProjectClient, innerAgent);
    }

    /// <summary>
    /// Creates a non-versioned <see cref="ChatClientAgent"/> backed by the project's Responses API using the specified model and instructions.
    /// </summary>
    /// <param name="aiProjectClient">The <see cref="AIProjectClient"/> to use for Responses API calls. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The model deployment name to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="name">Optional name for the agent.</param>
    /// <param name="description">Optional human-readable description for the agent.</param>
    /// <param name="tools">Optional collection of tools that the agent can invoke during conversations.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for creating loggers used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> backed by the project's Responses API.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    public static ChatClientAgent AsAIAgent(
        this AIProjectClient aiProjectClient,
        string model,
        string instructions,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        ChatClientAgentOptions options = new()
        {
            Name = name,
            Description = description,
            ChatOptions = new ChatOptions
            {
                ModelId = model,
                Instructions = instructions,
                Tools = tools,
            },
        };

        return CreateResponsesChatClientAgent(aiProjectClient, options, clientFactory, loggerFactory, services);
    }

    /// <summary>
    /// Creates a non-versioned <see cref="ChatClientAgent"/> backed by the project's Responses API using the specified options.
    /// </summary>
    /// <param name="aiProjectClient">The <see cref="AIProjectClient"/> to use for Responses API calls. Cannot be <see langword="null"/>.</param>
    /// <param name="options">Configuration options that control the agent's behavior. <see cref="ChatOptions.ModelId"/> is required.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for creating loggers used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> backed by the project's Responses API.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="options"/> does not specify <see cref="ChatOptions.ModelId"/>.</exception>
    public static ChatClientAgent AsAIAgent(
        this AIProjectClient aiProjectClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(options);

        return CreateResponsesChatClientAgent(aiProjectClient, options, clientFactory, loggerFactory, services);
    }

    #region Private

    /// <summary>Creates a <see cref="ChatClientAgent"/> with the specified options.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AIProjectClient aiProjectClient,
        ProjectsAgentVersion agentVersion,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIProjectChatClient(aiProjectClient, agentVersion, agentOptions.ChatOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    private static ChatClientAgent CreateResponsesChatClientAgent(
        AIProjectClient aiProjectClient,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        ILoggerFactory? loggerFactory,
        IServiceProvider? services)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentOptions);
        Throw.IfNull(agentOptions.ChatOptions);
        Throw.IfNullOrWhitespace(agentOptions.ChatOptions.ModelId);

        IChatClient chatClient = aiProjectClient
            .GetProjectOpenAIClient()
            .GetResponsesClient()
            .AsIChatClient(agentOptions.ChatOptions.ModelId);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, loggerFactory, services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent AsChatClientAgent(
        AIProjectClient aiProjectClient,
        ProjectsAgentVersion agentVersion,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
        => CreateChatClientAgent(aiProjectClient, agentVersion, agentOptions, clientFactory, services);

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent AsChatClientAgent(
        AIProjectClient aiProjectClient,
        ProjectsAgentRecord agentRecord,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIProjectChatClient(aiProjectClient, agentRecord, agentOptions.ChatOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent AsChatClientAgent(
        AIProjectClient aiProjectClient,
        AgentReference agentReference,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIProjectChatClient(aiProjectClient, agentReference, defaultModelId: null, agentOptions.ChatOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with a auto-generated ChatClientAgentOptions from the specified configuration parameters.</summary>
    private static ChatClientAgent AsChatClientAgent(
        AIProjectClient aiProjectClient,
        ProjectsAgentVersion agentVersion,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        bool requireInvocableTools,
        IServiceProvider? services)
        => AsChatClientAgent(
            aiProjectClient,
            agentVersion,
            CreateChatClientAgentOptions(agentVersion, new ChatOptions() { Tools = tools }, requireInvocableTools),
            clientFactory,
            services);

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with a auto-generated ChatClientAgentOptions from the specified configuration parameters.</summary>
    private static ChatClientAgent AsChatClientAgent(
        AIProjectClient aiProjectClient,
        ProjectsAgentRecord agentRecord,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        bool requireInvocableTools,
        IServiceProvider? services)
        => AsChatClientAgent(
            aiProjectClient,
            agentRecord,
            CreateChatClientAgentOptions(agentRecord.GetLatestVersion(), new ChatOptions() { Tools = tools }, requireInvocableTools),
            clientFactory,
            services);

    /// <summary>
    /// This method creates <see cref="ChatClientAgentOptions"/> for the specified <see cref="ProjectsAgentVersion"/> and the provided tools.
    /// </summary>
    /// <param name="agentVersion">The agent version.</param>
    /// <param name="chatOptions">The <see cref="ChatOptions"/> to use when interacting with the agent.</param>
    /// <param name="requireInvocableTools">Indicates whether to enforce the presence of invocable tools when the AIAgent is created with an agent definition that uses them.</param>
    /// <returns>The created <see cref="ChatClientAgentOptions"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the agent definition requires in-process tools but none were provided.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the agent definition required tools were not provided.</exception>
    /// <remarks>
    /// This method rebuilds the agent options from the agent definition returned by the version and combine with the in-proc tools when provided
    /// this ensures that all required tools are provided and the definition of the agent options are consistent with the agent definition coming from the server.
    /// </remarks>
    private static ChatClientAgentOptions CreateChatClientAgentOptions(ProjectsAgentVersion agentVersion, ChatOptions? chatOptions, bool requireInvocableTools)
    {
        var agentDefinition = agentVersion.Definition;

        List<AITool>? agentTools = null;
        if (agentDefinition is DeclarativeAgentDefinition { Tools: { Count: > 0 } definitionTools })
        {
            // Check if no tools were provided while the agent definition requires in-proc tools.
            if (requireInvocableTools && chatOptions?.Tools is not { Count: > 0 } && definitionTools.Any(t => t is FunctionTool))
            {
                throw new ArgumentException("The agent definition in-process tools must be provided in the extension method tools parameter.");
            }

            // Agregate all missing tools for a single error message.
            List<string>? missingTools = null;

            // Check function tools
            foreach (ResponseTool responseTool in definitionTools)
            {
                if (responseTool is FunctionTool functionTool)
                {
                    // Check if a tool with the same type and name exists in the provided tools.
                    // Always prefer matching AIFunction when available, regardless of requireInvocableTools.
                    var matchingTool = chatOptions?.Tools?.FirstOrDefault(t => t is AIFunction tf && functionTool.FunctionName == tf.Name);

                    if (matchingTool is not null)
                    {
                        (agentTools ??= []).Add(matchingTool!);
                        continue;
                    }

                    if (requireInvocableTools)
                    {
                        (missingTools ??= []).Add($"Function tool: {functionTool.FunctionName}");
                        continue;
                    }
                }

                (agentTools ??= []).Add(responseTool.AsAITool());
            }

            if (requireInvocableTools && missingTools is { Count: > 0 })
            {
                throw new InvalidOperationException($"The following prompt agent definition required tools were not provided: {string.Join(", ", missingTools)}");
            }
        }

        // Use the agent version's ID if available, otherwise generate one from name and version.
        // This handles cases where hosted agents (like MCP agents) may not have an ID assigned.
        var version = string.IsNullOrWhiteSpace(agentVersion.Version) ? "latest" : agentVersion.Version;
        var agentId = string.IsNullOrWhiteSpace(agentVersion.Id)
            ? $"{agentVersion.Name}:{version}"
            : agentVersion.Id;

        var agentOptions = new ChatClientAgentOptions()
        {
            Id = agentId,
            Name = agentVersion.Name,
            Description = agentVersion.Description,
        };

        if (agentDefinition is DeclarativeAgentDefinition promptAgentDefinition)
        {
            agentOptions.ChatOptions ??= chatOptions?.Clone() ?? new();
            agentOptions.ChatOptions.Instructions = promptAgentDefinition.Instructions;
            agentOptions.ChatOptions.Temperature = promptAgentDefinition.Temperature;
            agentOptions.ChatOptions.TopP = promptAgentDefinition.TopP;
        }

        if (agentTools is { Count: > 0 })
        {
            agentOptions.ChatOptions ??= chatOptions?.Clone() ?? new();
            agentOptions.ChatOptions.Tools = agentTools;
        }

        return agentOptions;
    }

#if NET
    [GeneratedRegex("^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")]
    private static partial Regex AgentNameValidationRegex();
#else
    private static Regex AgentNameValidationRegex() => new("^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$");
#endif

    internal static string ThrowIfInvalidAgentName(string? name)
    {
        Throw.IfNullOrWhitespace(name);
        if (!AgentNameValidationRegex().IsMatch(name))
        {
            throw new ArgumentException("Agent name must be 1-63 characters long, start and end with an alphanumeric character, and can only contain alphanumeric characters or hyphens.", nameof(name));
        }
        return name;
    }
}

[JsonSerializable(typeof(JsonElement))]
internal sealed partial class AgentClientJsonContext : JsonSerializerContext;

#endregion
