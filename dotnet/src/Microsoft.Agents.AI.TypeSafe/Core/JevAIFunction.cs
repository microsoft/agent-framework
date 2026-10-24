// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// The <see cref="AIFunction"/> created by <see cref="JevAIToolBuilder"/>: its arguments are a <see cref="JevRequest"/>
/// and its result is the <see cref="JevResult"/> of the configured mapping or the TypeSafe API.
/// </summary>
internal sealed class JevAIFunction : AIFunction
{
    private readonly Func<JevRequest, IServiceProvider?, CancellationToken, Task<JevResult>> _systemOneAsync;

    public JevAIFunction(string name, string description, Func<JevRequest, IServiceProvider?, CancellationToken, Task<JevResult>> systemOneAsync)
    {
        this.Name = name;
        this.Description = description;
        this._systemOneAsync = systemOneAsync;
    }

    public override string Name { get; }

    public override string Description { get; }

    public override JsonElement JsonSchema => JevJsonUtilities.RequestSchema;

    public override JsonElement? ReturnJsonSchema => JevJsonUtilities.ResultSchema;

    public override JsonSerializerOptions JsonSerializerOptions => JevJsonUtilities.Options;

    protected override async ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
    {
        JevRequest request = ReadRequest(arguments);
        JevContractValidator.ValidateRequest(request);

        // FunctionInvokingChatClient sets Services to the IServiceProvider of the agent (ChatClientAgent passes its
        // services through), so mappings can resolve per-call dependencies such as a registered client.
        JevResult? result = await this._systemOneAsync(request, arguments.Services, cancellationToken).ConfigureAwait(false);
        if (result is null)
        {
            Throw.InvalidOperationException("The Jev mapping returned no result.");
        }

        JevContractValidator.ValidateResult(request, result);

        // The result is returned as JSON, as AIFunctionFactory does. Chat clients serialize any other result object
        // with AIJsonUtilities.DefaultOptions, which has no metadata for these types when reflection is disabled
        // (for example under native AOT); the model would then receive an empty tool output.
        try
        {
            return JsonSerializer.SerializeToElement(result, JevJsonContext.Default.JevResult);
        }
        catch (Exception ex) when (ex is ArgumentException or JsonException or NotSupportedException)
        {
            // A result that cannot be written is a mapping fault. Reported as ArgumentException, it would look
            // like a mistake in the model's arguments and invite the model to retry the same call.
            throw new InvalidOperationException($"The Jev result could not be serialized: {ex.Message}", ex);
        }
    }

    private static JevRequest ReadRequest(AIFunctionArguments arguments)
    {
        // The arguments are the top-level properties of the request, so they are reassembled into one object.
        var json = new JsonObject();
        foreach (KeyValuePair<string, object?> argument in arguments)
        {
            json[argument.Key] = JevJsonUtilities.ToNode(argument.Value);
        }

        try
        {
            return json.Deserialize(JevJsonContext.Default.JevRequest)
                ?? throw new JsonException("The arguments are null.");
        }
        catch (Exception ex) when (ex is JsonException or NotSupportedException)
        {
            // An unknown or missing question type surfaces as NotSupportedException rather than JsonException.
            throw new ArgumentException($"The arguments are not a valid Jev request: {ex.Message}", nameof(arguments), ex);
        }
    }
}
