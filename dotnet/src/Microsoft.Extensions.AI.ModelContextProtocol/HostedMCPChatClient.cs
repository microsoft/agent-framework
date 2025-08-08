// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using ModelContextProtocol.Client;

namespace Microsoft.Extensions.AI.ModelContextProtocol;

/// <summary>
/// Adds support for enabling MCP function invocation.
/// </summary>
public class HostedMCPChatClient : DelegatingChatClient
{
    /// <summary>The logger to use for logging information about function invocation.</summary>
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionInvokingChatClientWithBuiltInApprovals"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying <see cref="IChatClient"/>, or the next instance in a chain of clients.</param>
    /// <param name="loggerFactory">An <see cref="ILoggerFactory"/> to use for logging information about function invocation.</param>
    public HostedMCPChatClient(IChatClient innerClient, ILoggerFactory? loggerFactory = null)
        : base(innerClient)
    {
        this._logger = (ILogger?)loggerFactory?.CreateLogger<FunctionInvokingChatClientWithBuiltInApprovals>() ?? NullLogger.Instance;
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        if (options?.Tools is not { Count: > 0 })
        {
            // If there are no tools, just call the inner client.
            return await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
        }

        List<AITool> downstreamTools = [];
        foreach (var tool in options.Tools ?? [])
        {
            if (tool is HostedMcpServerTool mcpTool)
            {
                // List all MCP functions from the specified MCP server.
                // This will need some caching in a real-world scenario to avoid repeated calls.
                var mcpClient = await CreateMcpClientAsync(mcpTool.Url).ConfigureAwait(false);
                var mcpFunctions = await mcpClient.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

                // Add the listed functions to our list of tools we'll pass to the inner client.
                foreach (var mcpFunction in mcpFunctions)
                {
                    if (mcpTool.AllowedTools is not null && !mcpTool.AllowedTools.Contains(mcpFunction.Name))
                    {
                        this._logger.LogInformation("MCP function '{FunctionName}' is not allowed by the tool configuration.", mcpFunction.Name);
                        continue;
                    }

                    switch (mcpTool.ApprovalMode)
                    {
                        case HostedMcpServerToolAlwaysRequireApprovalMode alwaysRequireApproval:
                            downstreamTools.Add(new ApprovalRequiredAIFunction(mcpFunction));
                            break;
                        case HostedMcpServerToolNeverRequireApprovalMode neverRequireApproval:
                            downstreamTools.Add(mcpFunction);
                            break;
                        case HostedMcpServerToolRequireSpecificApprovalMode specificApprovalMode when specificApprovalMode.AlwaysRequireApprovalToolNames?.Contains(mcpFunction.Name) is true:
                            downstreamTools.Add(new ApprovalRequiredAIFunction(mcpFunction));
                            break;
                        case HostedMcpServerToolRequireSpecificApprovalMode specificApprovalMode when specificApprovalMode.NeverRequireApprovalToolNames?.Contains(mcpFunction.Name) is true:
                            downstreamTools.Add(mcpFunction);
                            break;
                        default:
                            // Default to always require approval if no specific mode is set.
                            downstreamTools.Add(new ApprovalRequiredAIFunction(mcpFunction));
                            break;
                    }
                }

                // Skip adding the MCP tool itself, as we only want to add the functions it provides.
                continue;
            }

            // For other tools, we want to keep them in the list of tools.
            downstreamTools.Add(tool);
        }

        options = options.Clone();
        options.Tools = downstreamTools;

        // Make the call to the inner client.
        return await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
    }

    private static async Task<IMcpClient> CreateMcpClientAsync(Uri mcpService)
    {
        // Create mock MCP client for demonstration purposes.
        var clientTransport = new StdioClientTransport(new StdioClientTransportOptions
        {
            Name = "Everything",
            Command = "npx",
            Arguments = ["-y", "@modelcontextprotocol/server-everything"],
        });

        return await McpClientFactory.CreateAsync(clientTransport).ConfigureAwait(false);
    }
}
