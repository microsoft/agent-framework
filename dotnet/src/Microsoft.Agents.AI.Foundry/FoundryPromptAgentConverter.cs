// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

#pragma warning disable OPENAI001

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Shared internal implementation behind the public <c>ToPromptAgentAsync</c> extension methods
/// on <see cref="ChatClientAgent"/> and <see cref="FoundryAgent"/>. Converts a Foundry-backed
/// agent into a <see cref="ProjectsAgentDefinition"/> ready to publish via
/// <see cref="AgentAdministrationClient"/>.
/// </summary>
/// <remarks>
/// <para>
/// Dispatch by <see cref="FoundryChatClient"/> construction mode (reachable via
/// <see cref="IChatClient.GetService(Type, object?)"/>):
/// </para>
/// <list type="bullet">
/// <item><description><b>Responses Agent (Mode 1)</b>: synthesize a <see cref="DeclarativeAgentDefinition"/> from the agent's <see cref="ChatOptions"/>.</description></item>
/// <item><description><b>Prompt Agent (Mode 2, cached version)</b>: return the cached <see cref="ProjectsAgentVersion.Definition"/>.</description></item>
/// <item><description><b>Prompt Agent (Mode 2, AgentReference-only)</b>: fetch the latest version from the service and return its definition.</description></item>
/// <item><description><b>Agent Endpoint (Mode 3)</b>: throw — no local definition exists to convert.</description></item>
/// </list>
/// </remarks>
internal static class FoundryPromptAgentConverter
{
    /// <summary>Performs the conversion for an agent whose chat client and chat options are supplied.</summary>
    /// <param name="chatClient">The chat client extracted from the calling agent (must surface a <see cref="FoundryChatClient"/> via <see cref="IChatClient.GetService(Type, object?)"/>).</param>
    /// <param name="chatOptions">The agent's chat options (model id, instructions, temperature, top-p, tools). Required for the Responses Agent mode; ignored for the Prompt Agent mode.</param>
    /// <param name="cancellationToken">A token that can cancel a server-side fetch (Prompt Agent AgentReference path).</param>
    /// <returns>A <see cref="ProjectsAgentDefinition"/> suitable for <c>AgentAdministrationClient.CreateAgentVersionAsync</c>.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the chat client is not Foundry-backed, the agent was constructed via the Agent Endpoint mode, no model id is set for the Responses Agent mode, or an unsupported <see cref="AITool"/> is encountered.</exception>
    public static async Task<ProjectsAgentDefinition> ConvertAsync(IChatClient chatClient, ChatOptions? chatOptions, CancellationToken cancellationToken)
    {
        Throw.IfNull(chatClient);

        var foundryChatClient = chatClient.GetService<FoundryChatClient>()
            ?? throw new InvalidOperationException(
                "ToPromptAgentAsync requires a FoundryChatClient-backed agent. " +
                "The supplied agent's chat client does not expose a FoundryChatClient via GetService<FoundryChatClient>().");

        // Prompt Agent (Mode 2) with a cached server-side version (constructed via ProjectsAgentVersion or ProjectsAgentRecord).
        if (foundryChatClient.GetService<ProjectsAgentVersion>() is { } cachedVersion)
        {
            return cachedVersion.Definition;
        }

        // Prompt Agent (Mode 2) AgentReference-only: fetch the agent definition from the service.
        // Honor a pinned AgentReference.Version when present (Q-C fix); fall back to the latest
        // version only when the reference is unpinned ("", null, or "latest").
        if (foundryChatClient.GetService<AgentReference>() is { } agentReference)
        {
            var aiProjectClient = foundryChatClient.GetService<AIProjectClient>()
                ?? throw new InvalidOperationException(
                    "Cannot fetch the agent version because the FoundryChatClient does not expose an AIProjectClient.");

            if (!string.IsNullOrWhiteSpace(agentReference.Version)
                && !string.Equals(agentReference.Version, "latest", StringComparison.OrdinalIgnoreCase))
            {
                var pinnedVersion = await aiProjectClient.AgentAdministrationClient
                    .GetAgentVersionAsync(agentReference.Name, agentReference.Version, cancellationToken)
                    .ConfigureAwait(false);
                return pinnedVersion.Value.Definition;
            }

            var record = await aiProjectClient.AgentAdministrationClient
                .GetAgentAsync(agentReference.Name, cancellationToken)
                .ConfigureAwait(false);
            return record.Value.GetLatestVersion().Definition;
        }

        // Agent Endpoint (Mode 3): AgentName is set (parsed from URL) but no AgentReference exists
        // locally. The agent definition lives only on the server and is not retrievable through this
        // chat client, so conversion is not supported here.
        if (foundryChatClient.AgentName is not null)
        {
            throw new InvalidOperationException(
                "ToPromptAgentAsync is not supported for agents constructed via the Agent Endpoint mode (Mode 3); " +
                "no local definition exists to convert.");
        }

        // Responses Agent (Mode 1): synthesize from ChatOptions.
        return SynthesizeFromChatOptions(chatOptions);
    }

    private static DeclarativeAgentDefinition SynthesizeFromChatOptions(ChatOptions? chatOptions)
    {
        if (chatOptions is null || string.IsNullOrWhiteSpace(chatOptions.ModelId))
        {
            throw new InvalidOperationException(
                "ToPromptAgentAsync requires a model id on the agent's ChatOptions to synthesize a prompt agent definition.");
        }

        var definition = new DeclarativeAgentDefinition(chatOptions.ModelId!)
        {
            Instructions = chatOptions.Instructions,
            Temperature = chatOptions.Temperature,
            TopP = chatOptions.TopP,
        };

        if (chatOptions.Tools is { Count: > 0 } tools)
        {
            foreach (var tool in tools)
            {
                definition.Tools.Add(ConvertTool(tool));
            }
        }

        return definition;
    }

    private static ResponseTool ConvertTool(AITool tool)
    {
        Throw.IfNull(tool);

        if (tool is AIFunction function)
        {
            // strictModeEnabled is intentionally true to match the Python spec's
            // default behavior. JsonSchema on AIFunction is a JsonElement; serialize via its
            // string form so the payload matches what callers pass elsewhere in this codebase.
            return ResponseTool.CreateFunctionTool(
                function.Name,
                BinaryData.FromString(function.JsonSchema.ToString() ?? "{}"),
                strictModeEnabled: true,
                function.Description);
        }

        if (tool.GetService(typeof(ResponseTool)) is ResponseTool responseTool)
        {
            return responseTool;
        }

        throw new InvalidOperationException(
            $"Cannot convert AITool of type '{tool.GetType().Name}' to a ResponseTool. " +
            "Only AIFunction and AITool instances that wrap a ResponseTool (such as those produced by FoundryAITool factories) are supported.");
    }
}
