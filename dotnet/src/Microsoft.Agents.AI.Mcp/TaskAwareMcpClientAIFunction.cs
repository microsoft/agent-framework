// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Extensions.Tasks;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Mcp;

/// <summary>
/// An <see cref="AIFunction"/> wrapper around an <see cref="McpClientTool"/> that drives the
/// <see href="https://modelcontextprotocol.io/extensions/tasks/overview">MCP Tasks extension</see>
/// lifecycle on behalf of the agent's tool loop.
/// </summary>
/// <remarks>
/// <para>
/// The wrapper delegates extension negotiation, inline-result fallback, polling, and
/// <c>input_required</c> handling to
/// <see cref="McpTasksClientExtensions.CallToolWithPollingAsync"/>.
/// Its result projection matches <see cref="McpClientTool"/> so the agent's function-calling
/// loop is unaware whether the server used a task.
/// </para>
/// </remarks>
internal sealed class TaskAwareMcpClientAIFunction : AIFunction
{
    private readonly McpClient _client;
    private readonly McpClientTool _inner;

    internal TaskAwareMcpClientAIFunction(McpClient client, McpClientTool inner)
    {
        _ = Throw.IfNull(client);
        _ = Throw.IfNull(inner);

        this._client = client;
        this._inner = inner;
    }

    /// <inheritdoc />
    public override string Name => this._inner.Name;

    /// <inheritdoc />
    public override string Description => this._inner.Description;

    /// <inheritdoc />
    public override JsonElement JsonSchema => this._inner.JsonSchema;

    /// <inheritdoc />
    public override JsonElement? ReturnJsonSchema => this._inner.ReturnJsonSchema;

    /// <inheritdoc />
    public override JsonSerializerOptions JsonSerializerOptions => this._inner.JsonSerializerOptions;

    /// <inheritdoc />
    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments,
        CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(arguments);

        CallToolResult result = await this._client.CallToolWithPollingAsync(
            new CallToolRequestParams
            {
                Name = this._inner.ProtocolTool.Name,
                Arguments = ToArgumentsDictionary(arguments, this.JsonSerializerOptions),
            },
            cancellationToken: cancellationToken).ConfigureAwait(false);

        if (result.IsError is not true &&
            result.StructuredContent is null &&
            !HasApplicationResultMetadata(result.Meta))
        {
            switch (result.Content.Count)
            {
                case 1 when result.Content[0].ToAIContent(this.JsonSerializerOptions) is { } aiContent:
                    return aiContent;

                case > 1 when result.Content.Select(c => c.ToAIContent(this.JsonSerializerOptions)).ToArray() is { } aiContents &&
                    aiContents.All(static c => c is not null):
                    return aiContents;
            }
        }

        return JsonSerializer.SerializeToElement(
            result,
            McpJsonUtilities.DefaultOptions.GetTypeInfo<CallToolResult>());
    }

    private static Dictionary<string, JsonElement> ToArgumentsDictionary(
        AIFunctionArguments arguments,
        JsonSerializerOptions options)
    {
        var typeInfo = options.GetTypeInfo<object?>();
        Dictionary<string, JsonElement> result = new(arguments.Count);
        foreach (KeyValuePair<string, object?> argument in arguments)
        {
            result.Add(
                argument.Key,
                argument.Value is JsonElement element
                    ? element
                    : JsonSerializer.SerializeToElement(argument.Value, typeInfo));
        }

        return result;
    }

    private static bool HasApplicationResultMetadata(JsonObject? metadata)
    {
        if (metadata is null)
        {
            return false;
        }

        foreach (KeyValuePair<string, JsonNode?> property in metadata)
        {
            if (!string.Equals(property.Key, MetaKeys.ServerInfo, System.StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }
}
