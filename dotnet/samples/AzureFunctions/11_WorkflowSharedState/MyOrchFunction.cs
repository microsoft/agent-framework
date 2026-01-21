// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace SingleAgent;

public static class MyOrchFunction
{
    [Function(nameof(MyOrchFunction))]
    public static async Task<List<string>> RunOrchestratorAsync(
        [OrchestrationTrigger] TaskOrchestrationContext context)
    {
        ILogger logger = context.CreateReplaySafeLogger(nameof(MyOrchFunction));
        logger.LogInformation("Saying hello.");
        var outputs = new List<string>();

        // Replace name and input with values relevant for your Durable Functions Activity
        outputs.Add(await context.CallActivityAsync<string>(nameof(SayHello), "Tokyo"));
        outputs.Add(await context.CallActivityAsync<string>(nameof(SayHello), "Seattle"));
        outputs.Add(await context.CallActivityAsync<string>(nameof(SayHello), "London"));

        // returns ["Hello Tokyo!", "Hello Seattle!", "Hello London!"]
        return outputs;
    }

    [Function(nameof(SayHello))]
    public static string SayHello([ActivityTrigger] string name,
        TaskActivityContext taskActivityContext,
        FunctionContext functionContext)
    {
        ILogger logger = functionContext.GetLogger("SayHello");
        if (logger.IsEnabled(LogLevel.Information))
        {
            var instanceId = (string)functionContext.BindingContext.BindingData["instanceId"]!;
            logger.LogInformation("Saying hello to {Name} for instanceId:{InstanceId}", name, instanceId);
        }
        return $"Hello {name}!";
    }

    [Function("MyOrchFunction_HttpStart")]
    public static async Task<HttpResponseData> HttpStartAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "get", "post")] HttpRequestData req,
        [DurableClient] DurableTaskClient client,
        FunctionContext executionContext)
    {
        ILogger logger = executionContext.GetLogger("MyOrchFunction_HttpStart");

        // Function input comes from the request content.
        string instanceId = await client.ScheduleNewOrchestrationInstanceAsync(
            nameof(MyOrchFunction));
        if (logger.IsEnabled(LogLevel.Information))
        {
            logger.LogInformation("Started orchestration with ID = '{InstanceId}'.", instanceId);
        }

        // Returns an HTTP 202 response with an instance management payload.
        // See https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-http-api#start-orchestration
        return await client.CreateCheckStatusResponseAsync(req, instanceId);
    }
}
