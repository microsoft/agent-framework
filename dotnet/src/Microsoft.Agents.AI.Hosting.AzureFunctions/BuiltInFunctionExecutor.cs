// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Context.Features;
using Microsoft.Azure.Functions.Worker.Extensions.Mcp;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.Azure.Functions.Worker.Invocation;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// This implementation of function executor handles invocations using the built-in static methods for agent HTTP and entity functions.
/// </summary>
/// <remarks>By default, the Azure Functions worker generates function executor and that executor is used for function invocations.
/// But for the dummy HTTP function we create for agents (by augmenting the metadata), that executor will not have the code to handle that function since the entrypoint is a built-in static method.
/// </remarks>
internal sealed class BuiltInFunctionExecutor : IFunctionExecutor
{
    public async ValueTask ExecuteAsync(FunctionContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        // Acquire the input binding feature (fail fast if missing rather than null-forgiving operator).
        IFunctionInputBindingFeature? functionInputBindingFeature = context.Features.Get<IFunctionInputBindingFeature>();
        if (functionInputBindingFeature == null)
        {
            throw new InvalidOperationException("Function input binding feature is not available on the current context.");
        }

        FunctionInputBindingResult? inputBindingResults = await functionInputBindingFeature.BindFunctionInputAsync(context);
        if (inputBindingResults is not { Values: { } values })
        {
            throw new InvalidOperationException($"Function input binding failed for the invocation {context.InvocationId}");
        }

        HttpRequestData? httpRequestData = null;
        TaskEntityDispatcher? dispatcher = null;
        DurableTaskClient? durableTaskClient = null;
        ToolInvocationContext? mcpToolInvocationContext = null;

        foreach (var binding in values)
        {
            switch (binding)
            {
                case HttpRequestData request:
                    httpRequestData = request;
                    break;
                case TaskEntityDispatcher entityDispatcher:
                    dispatcher = entityDispatcher;
                    break;
                case DurableTaskClient client:
                    durableTaskClient = client;
                    break;
                case ToolInvocationContext toolContext:
                    mcpToolInvocationContext = toolContext;
                    break;
            }
        }

        if (durableTaskClient is null)
        {
            // This is not expected to happen since all built-in functions are
            // expected to have a Durable Task client binding.
            throw new InvalidOperationException($"Durable Task client binding is missing for the invocation {context.InvocationId}.");
        }

        if (context.FunctionDefinition.EntryPoint == BuiltInFunctions.RunAgentHttpFunctionEntryPoint)
        {
            if (httpRequestData == null)
            {
                throw new InvalidOperationException($"HTTP request data binding is missing for the invocation {context.InvocationId}.");
            }

            context.GetInvocationResult().Value = await BuiltInFunctions.RunAgentHttpAsync(
                   httpRequestData,
                   durableTaskClient,
                   context);
            return;
        }

        if (context.FunctionDefinition.EntryPoint == BuiltInFunctions.RunAgentEntityFunctionEntryPoint)
        {
            if (dispatcher is null)
            {
                throw new InvalidOperationException($"Task entity dispatcher binding is missing for the invocation {context.InvocationId}.");
            }

            await BuiltInFunctions.InvokeAgentAsync(
                dispatcher,
                durableTaskClient,
                context);
            return;
        }

        if (context.FunctionDefinition.EntryPoint == BuiltInFunctions.RunAgentMcpToolFunctionEntryPoint)
        {
            if (mcpToolInvocationContext is null)
            {
                throw new InvalidOperationException($"MCP tool invocation context binding is missing for the invocation {context.InvocationId}.");
            }

            context.GetInvocationResult().Value =
                await BuiltInFunctions.RunMcpToolAsync(mcpToolInvocationContext, durableTaskClient, context);
            return;
        }

        throw new InvalidOperationException($"Unsupported function entry point '{context.FunctionDefinition.EntryPoint}' for invocation {context.InvocationId}.");
    }
}
