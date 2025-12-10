// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;

namespace AgentOrchestration_Chaining;

public static class FunctionTriggers
{
    public sealed record TextResponse(string Text);

    [Function(nameof(RunOrchestrationAsync))]
    public static async Task<string> RunOrchestrationAsync([OrchestrationTrigger] TaskOrchestrationContext context)
    {
        DurableAIAgent writer = context.GetAgent("WriterAgent");
        AgentThread writerThread = writer.GetNewThread();

        AgentRunResponse<TextResponse> initial = await writer.RunAsync<TextResponse>(
            message: "Write a concise inspirational sentence about learning.",
            thread: writerThread);

        AgentRunResponse<TextResponse> refined = await writer.RunAsync<TextResponse>(
            message: $"Improve this further while keeping it under 25 words: {initial.Result.Text}",
            thread: writerThread);

        return refined.Result.Text;
    }

    // POST /singleagent/run
    [Function(nameof(StartOrchestrationAsync))]
    public static async Task<HttpResponseData> StartOrchestrationAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "singleagent/run")] HttpRequestData req,
        [DurableClient] DurableTaskClient client)
    {
        string instanceId = await client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: nameof(RunOrchestrationAsync));

        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        await response.WriteAsJsonAsync(new
        {
            message = "Single-agent orchestration started.",
            instanceId,
            statusQueryGetUri = GetStatusQueryGetUri(req, instanceId),
        });
        return response;
    }

    // GET /singleagent/status/{instanceId}
    [Function(nameof(GetOrchestrationStatusAsync))]
    public static async Task<HttpResponseData> GetOrchestrationStatusAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "get", Route = "singleagent/status/{instanceId}")] HttpRequestData req,
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
        return $"{authority}/api/singleagent/status/{instanceId}";
    }
}
