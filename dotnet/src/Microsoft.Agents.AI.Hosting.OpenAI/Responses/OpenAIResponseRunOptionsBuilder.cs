// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

#pragma warning disable MAAI001

internal static class OpenAIResponseRunOptionsBuilder
{
    public static AgentRunOptions? ToRunOptions(
        this CreateResponse request,
        OpenAIResponsesMapOptions mapOptions,
        AIAgent? agent = null,
        ILogger? logger = null,
        bool logConflicts = false)
    {
        OpenAIResponseRequestInfo requestInfo = request.ToRequestInfo();
        OpenAIClientFunctionToolsOptions? clientFunctionOptions = mapOptions.DangerouslyAllowClientFunctionTools;

        if (clientFunctionOptions is null || requestInfo.Tools is not { Count: > 0 } requestTools)
        {
            return mapOptions.RunOptionsFactory(requestInfo);
        }

        List<AITool>? clientFunctions = requestTools.ExtractClientFunctionTools(out List<System.Text.Json.JsonElement>? unsupportedTools);
        if (clientFunctions is not { Count: > 0 })
        {
            return mapOptions.RunOptionsFactory(requestInfo);
        }

        ThrowIfDuplicateClientFunctionNames(clientFunctions);

        // Accepted function declarations are handled here. Any other tool type remains visible to the
        // configured factory and is rejected by the default factory.
        requestInfo.Tools = unsupportedTools;
        AgentRunOptions? runOptions = mapOptions.RunOptionsFactory(requestInfo);
        OpenAIClientFunctionToolNameConflictBehaviorKind nameConflictBehavior =
            clientFunctionOptions.NameConflictBehavior.Kind;

        HashSet<string> hostedToolNames = GetHostedToolNames(agent, runOptions);
        List<string> conflictingNames = clientFunctions
            .Select(tool => tool.Name)
            .Where(hostedToolNames.Contains)
            .Distinct(StringComparer.Ordinal)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToList();

        if (conflictingNames.Count > 0)
        {
            switch (nameConflictBehavior)
            {
                case OpenAIClientFunctionToolNameConflictBehaviorKind.Reject:
                    throw CreateNameConflictException(conflictingNames);

                case OpenAIClientFunctionToolNameConflictBehaviorKind.Ignore:
                    clientFunctions.RemoveAll(tool => hostedToolNames.Contains(tool.Name));
                    if (logConflicts)
                    {
                        logger?.LogWarning(
                            "Ignoring client function tool declarations that conflict with hosted agent tools: {ToolNames}",
                            string.Join(", ", conflictingNames));
                    }
                    break;

                case OpenAIClientFunctionToolNameConflictBehaviorKind.AllowOverride:
                    break;
            }
        }

        return clientFunctions.Count > 0
            ? AddClientFunctions(runOptions, clientFunctions, nameConflictBehavior, logger)
            : runOptions;
    }

    private static ChatClientAgentRunOptions AddClientFunctions(
        AgentRunOptions? runOptions,
        List<AITool> clientFunctions,
        OpenAIClientFunctionToolNameConflictBehaviorKind nameConflictBehavior,
        ILogger? logger)
    {
        ChatClientAgentRunOptions chatRunOptions = runOptions switch
        {
            null => new ChatClientAgentRunOptions(),
            ChatClientAgentRunOptions existingRunOptions => (ChatClientAgentRunOptions)existingRunOptions.Clone(),
            _ => throw new NotSupportedException(
                $"{nameof(OpenAIResponsesMapOptions.DangerouslyAllowClientFunctionTools)} requires " +
                $"{nameof(OpenAIResponsesMapOptions.RunOptionsFactory)} to return null or {nameof(ChatClientAgentRunOptions)}.")
        };

        ChatOptions chatOptions = chatRunOptions.ChatOptions?.Clone() ?? new ChatOptions();
        chatOptions.AllowMultipleToolCalls = false;
        chatOptions.Tools = chatOptions.Tools is { Count: > 0 } existingTools
            ? [.. clientFunctions, .. existingTools]
            : [.. clientFunctions];
        chatRunOptions.ChatOptions = chatOptions;

        Func<IChatClient, IChatClient>? innerFactory = chatRunOptions.ChatClientFactory;
        chatRunOptions.ChatClientFactory = chatClient =>
        {
            IChatClient innerClient = innerFactory is null
                ? chatClient
                : innerFactory(chatClient) ?? throw new InvalidOperationException(
                    $"{nameof(ChatClientAgentRunOptions.ChatClientFactory)} returned null.");
            return new ClientFunctionToolConflictResolvingChatClient(innerClient, nameConflictBehavior, logger);
        };

        return chatRunOptions;
    }

    private static HashSet<string> GetHostedToolNames(AIAgent? agent, AgentRunOptions? runOptions)
    {
        var names = new HashSet<string>(StringComparer.Ordinal);

        AddToolNames(agent?.GetService<FunctionInvokingChatClient>()?.AdditionalTools, names);
        AddToolNames(agent?.GetService<ChatOptions>()?.Tools, names);
        AddToolNames((runOptions as ChatClientAgentRunOptions)?.ChatOptions?.Tools, names);

        return names;
    }

    private static void AddToolNames(IEnumerable<AITool>? tools, HashSet<string> names)
    {
        if (tools is null)
        {
            return;
        }

        foreach (AITool tool in tools)
        {
            if (tool is AIFunctionDeclaration && !string.IsNullOrEmpty(tool.Name))
            {
                names.Add(tool.Name);
            }
        }
    }

    private static void ThrowIfDuplicateClientFunctionNames(List<AITool> clientFunctions)
    {
        string? duplicateName = clientFunctions
            .GroupBy(tool => tool.Name, StringComparer.Ordinal)
            .FirstOrDefault(group => group.Count() > 1)
            ?.Key;

        if (duplicateName is not null)
        {
            throw new NotSupportedException(
                $"The request contains more than one client function tool named '{duplicateName}'.");
        }
    }

    private static NotSupportedException CreateNameConflictException(IReadOnlyList<string> conflictingNames) =>
        new(
            "Client function tool declarations conflict with tools configured by the hosted agent: " +
            $"{string.Join(", ", conflictingNames)}.");

    private sealed class ClientFunctionToolConflictResolvingChatClient : DelegatingChatClient
    {
        private readonly OpenAIClientFunctionToolNameConflictBehaviorKind _nameConflictBehavior;
        private readonly ILogger? _logger;
        private bool _loggedIgnoredConflicts;

        public ClientFunctionToolConflictResolvingChatClient(
            IChatClient innerClient,
            OpenAIClientFunctionToolNameConflictBehaviorKind nameConflictBehavior,
            ILogger? logger)
            : base(innerClient)
        {
            this._nameConflictBehavior = nameConflictBehavior;
            this._logger = logger;
        }

        public override Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default) =>
            base.GetResponseAsync(messages, this.ResolveNameConflicts(options), cancellationToken);

        public override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default) =>
            base.GetStreamingResponseAsync(messages, this.ResolveNameConflicts(options), cancellationToken);

        private ChatOptions? ResolveNameConflicts(ChatOptions? options)
        {
            if (options?.Tools is not { Count: > 0 } tools)
            {
                return options;
            }

            var clientNames = tools
                .OfType<OpenAIResponseRequestInfoBuilder.ClientAIFunctionDeclaration>()
                .Select(tool => tool.Name)
                .ToHashSet(StringComparer.Ordinal);
            if (clientNames.Count == 0)
            {
                return options;
            }

            List<string> conflictingNames = tools
                .Where(tool =>
                    tool is AIFunctionDeclaration and
                    not OpenAIResponseRequestInfoBuilder.ClientAIFunctionDeclaration)
                .Select(tool => tool.Name)
                .Where(clientNames.Contains)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(name => name, StringComparer.Ordinal)
                .ToList();
            if (conflictingNames.Count == 0)
            {
                return options;
            }

            if (this._nameConflictBehavior == OpenAIClientFunctionToolNameConflictBehaviorKind.Reject)
            {
                throw CreateNameConflictException(conflictingNames);
            }

            var conflictSet = conflictingNames.ToHashSet(StringComparer.Ordinal);
            ChatOptions resolvedOptions = options.Clone();
            resolvedOptions.Tools = this._nameConflictBehavior == OpenAIClientFunctionToolNameConflictBehaviorKind.Ignore
                ? tools.Where(tool =>
                    tool is not OpenAIResponseRequestInfoBuilder.ClientAIFunctionDeclaration ||
                    !conflictSet.Contains(tool.Name)).ToList()
                : tools.Where(tool =>
                    tool is OpenAIResponseRequestInfoBuilder.ClientAIFunctionDeclaration ||
                    tool is not AIFunctionDeclaration ||
                    !conflictSet.Contains(tool.Name)).ToList();

            if (this._nameConflictBehavior == OpenAIClientFunctionToolNameConflictBehaviorKind.Ignore &&
                !this._loggedIgnoredConflicts)
            {
                this._loggedIgnoredConflicts = true;
                this._logger?.LogWarning(
                    "Ignoring client function tool declarations that conflict with hosted agent tools: {ToolNames}",
                    string.Join(", ", conflictingNames));
            }

            return resolvedOptions;
        }
    }
}

#pragma warning restore MAAI001
