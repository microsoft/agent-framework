// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace LongRunningTools;

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
        DurableAIAgent writerAgent = context.GetAgent("Writer");
        AgentSession writerSession = await writerAgent.CreateSessionAsync();

        // Set initial status
        context.SetCustomStatus($"Starting content generation for topic: {input.Topic}");

        // Step 1: Generate initial content
        AgentResponse<GeneratedContent> writerResponse = await writerAgent.RunAsync<GeneratedContent>(
            message: $"Write a short article about '{input.Topic}'.",
            session: writerSession);
        GeneratedContent content = writerResponse.Result;

        // Human-in-the-loop iteration - we set a maximum number of attempts to avoid infinite loops
        int iterationCount = 0;
        while (iterationCount++ < input.MaxReviewAttempts)
        {
            // NOTE: CustomStatus has a 16 KB UTF-16 limit in Durable Functions.
            // Only include short metadata here - the full content is passed via activity inputs/outputs.
            context.SetCustomStatus(
                new
                {
                    message = "Requesting human feedback.",
                    approvalTimeoutHours = input.ApprovalTimeoutHours,
                    iterationCount,
                    contentTitle = content.Title,
                });

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
                    new
                    {
                        message = $"Human approval timed out after {input.ApprovalTimeoutHours} hour(s). Treating as rejection.",
                        iterationCount,
                    });
                throw new TimeoutException($"Human approval timed out after {input.ApprovalTimeoutHours} hour(s).");
            }

            if (humanResponse.Approved)
            {
                context.SetCustomStatus(new
                {
                    message = "Content approved by human reviewer. Publishing content...",
                    contentTitle = content.Title,
                });

                // Step 4: Publish the approved content
                await context.CallActivityAsync(nameof(PublishContent), content);

                context.SetCustomStatus(new
                {
                    message = $"Content published successfully at {context.CurrentUtcDateTime:s}",
                    humanFeedback = humanResponse,
                    contentTitle = content.Title,
                });
                return new { content = content.Content };
            }

            context.SetCustomStatus(new
            {
                message = "Content rejected by human reviewer. Incorporating feedback and regenerating...",
                humanFeedback = humanResponse,
                contentTitle = content.Title,
            });

            // Incorporate human feedback and regenerate
            writerResponse = await writerAgent.RunAsync<GeneratedContent>(
                message: $"""
                    The content was rejected by a human reviewer. Please rewrite the article incorporating their feedback.
                    
                    Human Feedback: {humanResponse.Feedback}
                    """,
                session: writerSession);

            content = writerResponse.Result;
        }

        // If we reach here, it means we exhausted the maximum number of iterations
        throw new InvalidOperationException(
            $"Content could not be approved after {input.MaxReviewAttempts} iterations.");
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
}
