// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Invocation;
using Microsoft.Azure.Functions.Worker.Middleware;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// This middleware sets a custom function executor for invocation of functions that have the built-in method as the entrypoint.
/// </summary>
internal sealed class BuiltInFunctionExecutionMiddleware(BuiltInFunctionExecutor builtInFunctionExecutor)
    : IFunctionsWorkerMiddleware
{
    private readonly BuiltInFunctionExecutor _builtInFunctionExecutor = builtInFunctionExecutor;

    public async Task Invoke(FunctionContext context, FunctionExecutionDelegate next)
    {
        // We set our custom function executor for this invocation.
        context.Features.Set<IFunctionExecutor>(this._builtInFunctionExecutor);

        await next(context);
    }
}
