// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;

namespace AgentOrchestration_Concurrency;

public static class FunctionsTriggers
{
    public sealed record TextResponse(string Text);

    [Function(nameof(RunOrchestrationAsync))]
    public static async Task<object> RunOrchestrationAsync([OrchestrationTrigger] TaskOrchestrationContext context)
    {
        // Get the prompt from the orchestration input
        string prompt = context.GetInput<string>() ?? throw new InvalidOperationException("Prompt is required");

        // Get both agents
        DurableAIAgent physicist = context.GetAgent("PhysicistAgent");
        DurableAIAgent chemist = context.GetAgent("ChemistAgent");

        // Start both agent runs concurrently
        Task<AgentRunResponse<TextResponse>> physicistTask = physicist.RunAsync<TextResponse>(prompt);

        Task<AgentRunResponse<TextResponse>> chemistTask = chemist.RunAsync<TextResponse>(prompt);

        // Wait for both tasks to complete using Task.WhenAll
        await Task.WhenAll(physicistTask, chemistTask);

        // Get the results
        TextResponse physicistResponse = (await physicistTask).Result;
        TextResponse chemistResponse = (await chemistTask).Result;

        // Return the result as a structured, anonymous type
        return new
        {
            physicist = physicistResponse.Text,
            chemist = chemistResponse.Text,
        };
    }

    // POST /multiagent/run
    [Function(nameof(StartOrchestrationAsync))]
    public static async Task<HttpResponseData> StartOrchestrationAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "multiagent/run")] HttpRequestData req,
        [DurableClient] DurableTaskClient client)
    {
        // Read the prompt from the request body
        string? prompt = await req.ReadAsStringAsync();
        if (string.IsNullOrWhiteSpace(prompt))
        {
            HttpResponseData badRequestResponse = req.CreateResponse(HttpStatusCode.BadRequest);
            await badRequestResponse.WriteAsJsonAsync(new { error = "Prompt is required" });
            return badRequestResponse;
        }

        string instanceId = await client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: nameof(RunOrchestrationAsync),
            input: prompt);

        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        await response.WriteAsJsonAsync(new
        {
            message = "Multi-agent concurrent orchestration started.",
            prompt,
            instanceId,
            statusQueryGetUri = GetStatusQueryGetUri(req, instanceId),
        });
        return response;
    }

    // GET /multiagent/status/{instanceId}
    [Function(nameof(GetOrchestrationStatusAsync))]
    public static async Task<HttpResponseData> GetOrchestrationStatusAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "get", Route = "multiagent/status/{instanceId}")] HttpRequestData req,
        string instanceId,
        [DurableClient] DurableTaskClient client)
    {
        OrchestrationMetadata? status = await client.GetInstanceAsync(
            instanceId,
            getInputsAndOutputs: true,
            req.FunctionContext.CancellationToken);

        if (status is null)
        {
            HttpResponseData notFound = req.CreateResponse(HttpStatusCode.NotFound);
            await notFound.WriteAsJsonAsync(new { error = "Instance not found" });
            return notFound;
        }

        HttpResponseData response = req.CreateResponse(HttpStatusCode.OK);
        await response.WriteAsJsonAsync(new
        {
            instanceId = status.InstanceId,
            runtimeStatus = status.RuntimeStatus.ToString(),
            input = status.SerializedInput is not null ? (object)status.ReadInputAs<JsonElement>() : null,
            output = status.SerializedOutput is not null ? (object)status.ReadOutputAs<JsonElement>() : null,
            failureDetails = status.FailureDetails
        });
        return response;
    }

    private static string GetStatusQueryGetUri(HttpRequestData req, string instanceId)
    {
        // NOTE: This can be made more robust by considering the value of
        //       request headers like "X-Forwarded-Host" and "X-Forwarded-Proto".
        string authority = $"{req.Url.Scheme}://{req.Url.Authority}";
        return $"{authority}/api/multiagent/status/{instanceId}";
    }
}
