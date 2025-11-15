// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace AgentOrchestration_HITL;

public static class FunctionTriggers
{
    [Function(nameof(RunOrchestrationAsync))]
    public static async Task<object> RunOrchestrationAsync(
        [OrchestrationTrigger] TaskOrchestrationContext context)
    {
        // Get the input from the orchestration
        ContentGenerationInput input = context.GetInput<ContentGenerationInput>()
            ?? throw new InvalidOperationException("Content generation input is required");

        // Get the writer agent
        DurableAIAgent writerAgent = context.GetAgent("WriterAgent");
        AgentThread writerThread = writerAgent.GetNewThread();

        // Set initial status
        context.SetCustomStatus($"Starting content generation for topic: {input.Topic}");

        // Step 1: Generate initial content
        AgentRunResponse<GeneratedContent> writerResponse = await writerAgent.RunAsync<GeneratedContent>(
            message: $"Write a short article about '{input.Topic}'.",
            thread: writerThread);
        GeneratedContent content = writerResponse.Result;

        // Human-in-the-loop iteration - we set a maximum number of attempts to avoid infinite loops
        int iterationCount = 0;
        while (iterationCount++ < input.MaxReviewAttempts)
        {
            context.SetCustomStatus(
                $"Requesting human feedback. Iteration #{iterationCount}. Timeout: {input.ApprovalTimeoutHours} hour(s).");

            // Step 2: Notify user to review the content
            await context.CallActivityAsync(nameof(NotifyUserForApproval), content);

            // Step 3: Wait for human feedback with configurable timeout
            HumanApprovalResponse humanResponse;
            try
            {
                humanResponse = await context.WaitForExternalEvent<HumanApprovalResponse>(
                    eventName: "HumanApproval",
                    timeout: TimeSpan.FromHours(input.ApprovalTimeoutHours));
            }
            catch (OperationCanceledException)
            {
                // Timeout occurred - treat as rejection
                context.SetCustomStatus(
                    $"Human approval timed out after {input.ApprovalTimeoutHours} hour(s). Treating as rejection.");
                throw new TimeoutException($"Human approval timed out after {input.ApprovalTimeoutHours} hour(s).");
            }

            if (humanResponse.Approved)
            {
                context.SetCustomStatus("Content approved by human reviewer. Publishing content...");

                // Step 4: Publish the approved content
                await context.CallActivityAsync(nameof(PublishContent), content);

                context.SetCustomStatus($"Content published successfully at {context.CurrentUtcDateTime:s}");
                return new { content = content.Content };
            }

            context.SetCustomStatus("Content rejected by human reviewer. Incorporating feedback and regenerating...");

            // Incorporate human feedback and regenerate
            writerResponse = await writerAgent.RunAsync<GeneratedContent>(
                message: $"""
                    The content was rejected by a human reviewer. Please rewrite the article incorporating their feedback.
                    
                    Human Feedback: {humanResponse.Feedback}
                    """,
                thread: writerThread);

            content = writerResponse.Result;
        }

        // If we reach here, it means we exhausted the maximum number of iterations
        throw new InvalidOperationException(
            $"Content could not be approved after {input.MaxReviewAttempts} iterations.");
    }

    // POST /hitl/run
    [Function(nameof(StartOrchestrationAsync))]
    public static async Task<HttpResponseData> StartOrchestrationAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "hitl/run")] HttpRequestData req,
        [DurableClient] DurableTaskClient client)
    {
        // Read the input from the request body
        ContentGenerationInput? input = await req.ReadFromJsonAsync<ContentGenerationInput>();
        if (input is null || string.IsNullOrWhiteSpace(input.Topic))
        {
            HttpResponseData badRequestResponse = req.CreateResponse(HttpStatusCode.BadRequest);
            await badRequestResponse.WriteAsJsonAsync(new { error = "Topic is required" });
            return badRequestResponse;
        }

        string instanceId = await client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: nameof(RunOrchestrationAsync),
            input: input);

        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        await response.WriteAsJsonAsync(new
        {
            message = "HITL content generation orchestration started.",
            topic = input.Topic,
            instanceId,
            statusQueryGetUri = GetStatusQueryGetUri(req, instanceId),
        });
        return response;
    }

    // POST /hitl/approve/{instanceId}
    [Function(nameof(SendHumanApprovalAsync))]
    public static async Task<HttpResponseData> SendHumanApprovalAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "hitl/approve/{instanceId}")] HttpRequestData req,
        string instanceId,
        [DurableClient] DurableTaskClient client)
    {
        // Read the approval response from the request body
        HumanApprovalResponse? approvalResponse = await req.ReadFromJsonAsync<HumanApprovalResponse>();
        if (approvalResponse is null)
        {
            HttpResponseData badRequestResponse = req.CreateResponse(HttpStatusCode.BadRequest);
            await badRequestResponse.WriteAsJsonAsync(new { error = "Approval response is required" });
            return badRequestResponse;
        }

        // Send the approval event to the orchestration
        await client.RaiseEventAsync(instanceId, "HumanApproval", approvalResponse);

        HttpResponseData response = req.CreateResponse(HttpStatusCode.OK);
        await response.WriteAsJsonAsync(new
        {
            message = "Human approval sent to orchestration.",
            instanceId,
            approved = approvalResponse.Approved
        });
        return response;
    }

    // GET /hitl/status/{instanceId}
    [Function(nameof(GetOrchestrationStatusAsync))]
    public static async Task<HttpResponseData> GetOrchestrationStatusAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "get", Route = "hitl/status/{instanceId}")] HttpRequestData req,
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
            workflowStatus = status.SerializedCustomStatus is not null ? (object)status.ReadCustomStatusAs<JsonElement>() : null,
            input = status.SerializedInput is not null ? (object)status.ReadInputAs<JsonElement>() : null,
            output = status.SerializedOutput is not null ? (object)status.ReadOutputAs<JsonElement>() : null,
            failureDetails = status.FailureDetails
        });
        return response;
    }

    [Function(nameof(NotifyUserForApproval))]
    public static void NotifyUserForApproval(
        [ActivityTrigger] GeneratedContent content,
        FunctionContext functionContext)
    {
        ILogger logger = functionContext.GetLogger(nameof(NotifyUserForApproval));

        // In a real implementation, this would send notifications via email, SMS, etc.
        logger.LogInformation(
            """
            NOTIFICATION: Please review the following content for approval:
            Title: {Title}
            Content: {Content}
            Use the approval endpoint to approve or reject this content.
            """,
            content.Title,
            content.Content);
    }

    [Function(nameof(PublishContent))]
    public static void PublishContent(
        [ActivityTrigger] GeneratedContent content,
        FunctionContext functionContext)
    {
        ILogger logger = functionContext.GetLogger(nameof(PublishContent));

        // In a real implementation, this would publish to a CMS, website, etc.
        logger.LogInformation(
            """
            PUBLISHING: Content has been published successfully.
            Title: {Title}
            Content: {Content}
            """,
            content.Title,
            content.Content);
    }

    private static string GetStatusQueryGetUri(HttpRequestData req, string instanceId)
    {
        // NOTE: This can be made more robust by considering the value of
        //       request headers like "X-Forwarded-Host" and "X-Forwarded-Proto".
        string authority = $"{req.Url.Scheme}://{req.Url.Authority}";
        return $"{authority}/api/hitl/status/{instanceId}";
    }
}
