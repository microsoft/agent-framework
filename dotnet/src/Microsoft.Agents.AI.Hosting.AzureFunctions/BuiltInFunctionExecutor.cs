// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Context.Features;
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
            }
        }

        bool isAgentHttpInvocation = string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal);

        if (isAgentHttpInvocation)
        {
            if (httpRequestData == null)
            {
                throw new InvalidOperationException($"HTTP request data binding is missing for the invocation {context.InvocationId}.");
            }
            if (durableTaskClient == null)
            {
                throw new InvalidOperationException($"Durable Task client binding is missing for the invocation {context.InvocationId}.");
            }

            context.GetInvocationResult().Value = await BuiltInFunctions.RunAgentHttpAsync(
                   httpRequestData,
                   durableTaskClient,
                   context);
            return;
        }

        // If not HTTP invocation, It will be entity invocation path.
        if (dispatcher == null)
        {
            throw new InvalidOperationException($"Task entity dispatcher binding is missing for the invocation {context.InvocationId}.");
        }
        if (durableTaskClient == null)
        {
            throw new InvalidOperationException($"Durable Task client binding is missing for the invocation {context.InvocationId}.");
        }

        await BuiltInFunctions.InvokeAgentAsync(
            dispatcher,
            durableTaskClient,
            context);
    }
}
