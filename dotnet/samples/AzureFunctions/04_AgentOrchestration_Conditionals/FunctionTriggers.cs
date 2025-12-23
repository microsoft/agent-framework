// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;

namespace AgentOrchestration_Conditionals;

public static class FunctionTriggers
{
    [Function(nameof(RunOrchestrationAsync))]
    public static async Task<string> RunOrchestrationAsync([OrchestrationTrigger] TaskOrchestrationContext context)
    {
        // Get the email from the orchestration input
        Email email = context.GetInput<Email>() ?? throw new InvalidOperationException("Email is required");

        // Get the spam detection agent
        DurableAIAgent spamDetectionAgent = context.GetAgent("SpamDetectionAgent");
        AgentThread spamThread = spamDetectionAgent.GetNewThread();

        // Step 1: Check if the email is spam
        AgentRunResponse<DetectionResult> spamDetectionResponse = await spamDetectionAgent.RunAsync<DetectionResult>(
            message:
                $"""
                Analyze this email for spam content and return a JSON response with 'is_spam' (boolean) and 'reason' (string) fields:
                Email ID: {email.EmailId}
                Content: {email.EmailContent}
                """,
            thread: spamThread);
        DetectionResult result = spamDetectionResponse.Result;

        // Step 2: Conditional logic based on spam detection result
        if (result.IsSpam)
        {
            // Handle spam email
            return await context.CallActivityAsync<string>(nameof(HandleSpamEmail), result.Reason);
        }

        // Generate and send response for legitimate email
        DurableAIAgent emailAssistantAgent = context.GetAgent("EmailAssistantAgent");
        AgentThread emailThread = emailAssistantAgent.GetNewThread();

        AgentRunResponse<EmailResponse> emailAssistantResponse = await emailAssistantAgent.RunAsync<EmailResponse>(
            message:
                $"""
                    Draft a professional response to this email. Return a JSON response with a 'response' field containing the reply:
                    
                    Email ID: {email.EmailId}
                    Content: {email.EmailContent}
                    """,
            thread: emailThread);

        EmailResponse emailResponse = emailAssistantResponse.Result;

        return await context.CallActivityAsync<string>(nameof(SendEmail), emailResponse.Response);
    }

    [Function(nameof(HandleSpamEmail))]
    public static string HandleSpamEmail([ActivityTrigger] string reason)
    {
        return $"Email marked as spam: {reason}";
    }

    [Function(nameof(SendEmail))]
    public static string SendEmail([ActivityTrigger] string message)
    {
        return $"Email sent: {message}";
    }

    // POST /spamdetection/run
    [Function(nameof(StartOrchestrationAsync))]
    public static async Task<HttpResponseData> StartOrchestrationAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "spamdetection/run")] HttpRequestData req,
        [DurableClient] DurableTaskClient client)
    {
        // Read the email from the request body
        Email? email = await req.ReadFromJsonAsync<Email>();
        if (email is null || string.IsNullOrWhiteSpace(email.EmailContent))
        {
            HttpResponseData badRequestResponse = req.CreateResponse(HttpStatusCode.BadRequest);
            await badRequestResponse.WriteAsJsonAsync(new { error = "Email with content is required" });
            return badRequestResponse;
        }

        string instanceId = await client.ScheduleNewOrchestrationInstanceAsync(
            orchestratorName: nameof(RunOrchestrationAsync),
            input: email);

        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        await response.WriteAsJsonAsync(new
        {
            message = "Spam detection orchestration started.",
            emailId = email.EmailId,
            instanceId,
            statusQueryGetUri = GetStatusQueryGetUri(req, instanceId),
        });
        return response;
    }

    // GET /spamdetection/status/{instanceId}
    [Function(nameof(GetOrchestrationStatusAsync))]
    public static async Task<HttpResponseData> GetOrchestrationStatusAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "get", Route = "spamdetection/status/{instanceId}")] HttpRequestData req,
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
        return $"{authority}/api/spamdetection/status/{instanceId}";
    }
}
