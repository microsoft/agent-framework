// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

/// <summary>
/// Integration tests for validating the durable agent console app samples
/// located in samples/Durable/Agents/ConsoleApps.
/// </summary>
[Collection("Samples")]
[Trait("Category", "SampleValidation")]
public sealed class ConsoleAppSamplesValidation(ITestOutputHelper outputHelper) : SamplesValidationBase(outputHelper)
{
    private static readonly string s_samplesPath = Path.GetFullPath(
        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", "..", "..", "samples", "Durable", "Agents", "ConsoleApps"));

    /// <inheritdoc />
    protected override string SamplesPath => s_samplesPath;

    /// <inheritdoc />
    protected override bool RequiresRedis => true;

    /// <inheritdoc />
    protected override void ConfigureAdditionalEnvironmentVariables(ProcessStartInfo startInfo, Action<string, string> setEnvVar)
    {
        setEnvVar("REDIS_CONNECTION_STRING", $"localhost:{RedisPort}");
    }

    [Fact]
    public async Task SingleAgentSampleValidationAsync()
    {
        using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();
        string samplePath = Path.Combine(s_samplesPath, "01_SingleAgent");
        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            string agentResponse = string.Empty;
            bool inputSent = false;

            // Read output from logs queue
            string? line;
            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                // Look for the agent's response. Unlike the interactive mode, we won't actually see a line
                // that starts with "Joker: ". Instead, we'll see a line that looks like "You: Joker: ..." because
                // the standard input is *not* echoed back to standard output.
                if (line.Contains("Joker: ", StringComparison.OrdinalIgnoreCase))
                {
                    // This will give us the first line of the agent's response, which is all we need to verify that the agent is working.
                    agentResponse = line.Substring("Joker: ".Length).Trim();
                    break;
                }
                else if (!inputSent)
                {
                    // Send input to stdin after we've started seeing output from the app
                    await this.WriteInputAsync(process, "Tell me a joke about a pirate.", testTimeoutCts.Token);
                    inputSent = true;
                }
            }

            Assert.True(inputSent, "Input was not sent to the agent");
            Assert.NotEmpty(agentResponse);

            // Send exit command
            await this.WriteInputAsync(process, "exit", testTimeoutCts.Token);
        });
    }

    [Fact]
    public async Task SingleAgentOrchestrationChainingSampleValidationAsync()
    {
        using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();
        string samplePath = Path.Combine(s_samplesPath, "02_AgentOrchestration_Chaining");
        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            // Console app runs automatically, just wait for completion
            string? line;
            bool foundSuccess = false;

            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                if (line.Contains("Orchestration completed successfully!", StringComparison.OrdinalIgnoreCase))
                {
                    foundSuccess = true;
                }

                if (line.Contains("Result:", StringComparison.OrdinalIgnoreCase))
                {
                    string result = line.Substring("Result:".Length).Trim();
                    Assert.NotEmpty(result);
                    break;
                }

                // Check for failure
                if (line.Contains("Orchestration failed!", StringComparison.OrdinalIgnoreCase))
                {
                    Assert.Fail("Orchestration failed.");
                }
            }

            Assert.True(foundSuccess, "Orchestration did not complete successfully.");
        });
    }

    [Fact]
    public async Task MultiAgentConcurrencySampleValidationAsync()
    {
        using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();
        string samplePath = Path.Combine(s_samplesPath, "03_AgentOrchestration_Concurrency");
        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            // Send input to stdin
            await this.WriteInputAsync(process, "What is temperature?", testTimeoutCts.Token);

            // Read output from logs queue
            StringBuilder output = new();
            string? line;
            bool foundSuccess = false;
            bool foundPhysicist = false;
            bool foundChemist = false;

            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                output.AppendLine(line);

                if (line.Contains("Orchestration completed successfully!", StringComparison.OrdinalIgnoreCase))
                {
                    foundSuccess = true;
                }

                if (line.Contains("Physicist's response:", StringComparison.OrdinalIgnoreCase))
                {
                    foundPhysicist = true;
                }

                if (line.Contains("Chemist's response:", StringComparison.OrdinalIgnoreCase))
                {
                    foundChemist = true;
                }

                // Check for failure
                if (line.Contains("Orchestration failed!", StringComparison.OrdinalIgnoreCase))
                {
                    Assert.Fail("Orchestration failed.");
                }

                // Stop reading once we have both responses
                if (foundSuccess && foundPhysicist && foundChemist)
                {
                    break;
                }
            }

            Assert.True(foundSuccess, "Orchestration did not complete successfully.");
            Assert.True(foundPhysicist, "Physicist response not found.");
            Assert.True(foundChemist, "Chemist response not found.");
        });
    }

    [Fact]
    public async Task MultiAgentConditionalSampleValidationAsync()
    {
        using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();
        string samplePath = Path.Combine(s_samplesPath, "04_AgentOrchestration_Conditionals");
        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            // Test with legitimate email
            await this.TestSpamDetectionAsync(
                process: process,
                logs: logs,
                emailId: "email-001",
                emailContent: "Hi John. I wanted to follow up on our meeting yesterday about the quarterly report. Could you please send me the updated figures by Friday? Thanks!",
                expectedSpam: false,
                testTimeoutCts.Token);

            // Restart the process for the second test
            await process.WaitForExitAsync();
        });

        // Run second test with spam email
        using CancellationTokenSource testTimeoutCts2 = this.CreateTestTimeoutCts();
        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            await this.TestSpamDetectionAsync(
                process,
                logs,
                emailId: "email-002",
                emailContent: "URGENT! You've won $1,000,000! Click here now to claim your prize! Limited time offer! Don't miss out!",
                expectedSpam: true,
                testTimeoutCts2.Token);
        });
    }

    private async Task TestSpamDetectionAsync(
        Process process,
        BlockingCollection<OutputLog> logs,
        string emailId,
        string emailContent,
        bool expectedSpam,
        CancellationToken cancellationToken)
    {
        // Send email content to stdin
        await this.WriteInputAsync(process, emailContent, cancellationToken);

        // Read output from logs queue
        string? line;
        bool foundSuccess = false;

        while ((line = this.ReadLogLine(logs, cancellationToken)) != null)
        {
            if (line.Contains("Email sent", StringComparison.OrdinalIgnoreCase))
            {
                Assert.False(expectedSpam, "Email was sent, but was expected to be marked as spam.");
            }

            if (line.Contains("Email marked as spam", StringComparison.OrdinalIgnoreCase))
            {
                Assert.True(expectedSpam, "Email was marked as spam, but was expected to be sent.");
            }

            if (line.Contains("Orchestration completed successfully!", StringComparison.OrdinalIgnoreCase))
            {
                foundSuccess = true;
                break;
            }

            // Check for failure
            if (line.Contains("Orchestration failed!", StringComparison.OrdinalIgnoreCase))
            {
                Assert.Fail("Orchestration failed.");
            }
        }

        Assert.True(foundSuccess, "Orchestration did not complete successfully.");
    }

    [Fact]
    public async Task SingleAgentOrchestrationHITLSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "05_AgentOrchestration_HITL");

        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();

            // Start the HITL orchestration following the happy path from README
            await this.WriteInputAsync(process, "The Future of Artificial Intelligence", testTimeoutCts.Token);
            await this.WriteInputAsync(process, "3", testTimeoutCts.Token);
            await this.WriteInputAsync(process, "72", testTimeoutCts.Token);

            // Read output from logs queue
            string? line;
            bool rejectionSent = false;
            bool approvalSent = false;
            bool contentPublished = false;

            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                // Look for notification that content is ready. The first time we see this, we should send a rejection.
                // The second time we see this, we should send approval.
                if (line.Contains("Content is ready for review", StringComparison.OrdinalIgnoreCase))
                {
                    if (!rejectionSent)
                    {
                        // Prompt: Approve? (y/n):
                        await this.WriteInputAsync(process, "n", testTimeoutCts.Token);

                        // Prompt: Feedback (optional):
                        await this.WriteInputAsync(
                            process,
                            "The article needs more technical depth and better examples. Rewrite it with less than 300 words.",
                            testTimeoutCts.Token);
                        rejectionSent = true;
                    }
                    else if (!approvalSent)
                    {
                        // Prompt: Approve? (y/n):
                        await this.WriteInputAsync(process, "y", testTimeoutCts.Token);

                        // Prompt: Feedback (optional):
                        await this.WriteInputAsync(process, "Looks good!", testTimeoutCts.Token);
                        approvalSent = true;
                    }
                    else
                    {
                        // This should never happen
                        Assert.Fail("Unexpected message found.");
                    }
                }

                // Look for success message
                if (line.Contains("PUBLISHING: Content has been published", StringComparison.OrdinalIgnoreCase))
                {
                    contentPublished = true;
                    break;
                }

                // Check for failure
                if (line.Contains("Orchestration failed", StringComparison.OrdinalIgnoreCase))
                {
                    Assert.Fail("Orchestration failed.");
                }
            }

            Assert.True(rejectionSent, "Wasn't prompted with the first draft.");
            Assert.True(approvalSent, "Wasn't prompted with the second draft.");
            Assert.True(contentPublished, "Content was not published.");
        });
    }

    [Fact]
    public async Task LongRunningToolsSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "06_LongRunningTools");
        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            // This test takes a bit longer to run due to the multiple agent interactions and the lengthy content generation.
            using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts(TimeSpan.FromSeconds(90));

            // Test starting an agent that schedules a content generation orchestration
            await this.WriteInputAsync(
                process,
                "Start a content generation workflow for the topic 'The Future of Artificial Intelligence'. Keep it less than 300 words.",
                testTimeoutCts.Token);

            // Read output from logs queue
            bool rejectionSent = false;
            bool approvalSent = false;
            bool contentPublished = false;

            string? line;
            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                // Look for notification that content is ready. The first time we see this, we should send a rejection.
                // The second time we see this, we should send approval.
                if (line.Contains("NOTIFICATION: Please review the following content for approval", StringComparison.OrdinalIgnoreCase))
                {
                    // Wait for the notification to be fully written to the console
                    await Task.Delay(TimeSpan.FromSeconds(1), testTimeoutCts.Token);

                    if (!rejectionSent)
                    {
                        // Reject the content with feedback. Note that we need to send a newline character to the console first before sending the input.
                        await this.WriteInputAsync(
                            process,
                            "\nReject the content with feedback: Make it even shorter.",
                            testTimeoutCts.Token);
                        rejectionSent = true;
                    }
                    else if (!approvalSent)
                    {
                        // Approve the content. Note that we need to send a newline character to the console first before sending the input.
                        await this.WriteInputAsync(
                            process,
                            "\nApprove the content",
                            testTimeoutCts.Token);
                        approvalSent = true;
                    }
                    else
                    {
                        // This should never happen
                        Assert.Fail("Unexpected message found.");
                    }
                }

                // Look for success message
                if (line.Contains("PUBLISHING: Content has been published successfully", StringComparison.OrdinalIgnoreCase))
                {
                    contentPublished = true;

                    // Ask for the status of the workflow to confirm that it completed successfully.
                    await Task.Delay(TimeSpan.FromSeconds(1), testTimeoutCts.Token);
                    await this.WriteInputAsync(process, "\nGet the status of the workflow you previously started", testTimeoutCts.Token);
                }

                // Check for workflow completion or failure
                if (contentPublished)
                {
                    if (line.Contains("Completed", StringComparison.OrdinalIgnoreCase))
                    {
                        break;
                    }
                    else if (line.Contains("Failed", StringComparison.OrdinalIgnoreCase))
                    {
                        Assert.Fail("Workflow failed.");
                    }
                }
            }

            Assert.True(rejectionSent, "Wasn't prompted with the first draft.");
            Assert.True(approvalSent, "Wasn't prompted with the second draft.");
            Assert.True(contentPublished, "Content was not published.");
        });
    }

    [Fact]
    public async Task ReliableStreamingSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "07_ReliableStreaming");
        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            // This test takes a bit longer to run due to the multiple agent interactions and the lengthy content generation.
            using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts(TimeSpan.FromSeconds(90));

            // Test the agent endpoint with a simple prompt
            await this.WriteInputAsync(process, "Plan a 5-day trip to Seattle. Include daily activities.", testTimeoutCts.Token);

            // Read output from stdout - should stream in real-time
            // NOTE: The sample uses Console.Write() for streaming chunks, which means content may not be line-buffered.
            // We test the interrupt/resume flow by:
            // 1. Waiting for at least 10 lines of content
            // 2. Sending Enter to interrupt
            // 3. Verifying we get "Last cursor" output
            // 4. Sending Enter again to resume
            // 5. Verifying we get more content and that we're not restarting from the beginning
            string? line;
            bool foundConversationStart = false;
            int contentLinesBeforeInterrupt = 0;
            int contentLinesAfterResume = 0;
            bool foundLastCursor = false;
            bool foundResumeMessage = false;
            bool interrupted = false;
            bool resumed = false;

            // Read output with a reasonable timeout
            using CancellationTokenSource readTimeoutCts = this.CreateTestTimeoutCts();
            DateTime? interruptTime = null;
            try
            {
                while ((line = this.ReadLogLine(logs, readTimeoutCts.Token)) != null)
                {
                    // Look for the conversation start message (updated format)
                    if (line.Contains("Conversation ID", StringComparison.OrdinalIgnoreCase))
                    {
                        foundConversationStart = true;
                        continue;
                    }

                    // Check if this is a content line (not prompts or status messages)
                    bool isContentLine = !string.IsNullOrWhiteSpace(line) &&
                        !line.Contains("Conversation ID", StringComparison.OrdinalIgnoreCase) &&
                        !line.Contains("Press [Enter]", StringComparison.OrdinalIgnoreCase) &&
                        !line.Contains("You:", StringComparison.OrdinalIgnoreCase) &&
                        !line.Contains("exit", StringComparison.OrdinalIgnoreCase) &&
                        !line.Contains("Stream cancelled", StringComparison.OrdinalIgnoreCase) &&
                        !line.Contains("Resuming conversation", StringComparison.OrdinalIgnoreCase) &&
                        !line.Contains("Last cursor", StringComparison.OrdinalIgnoreCase);

                    // Phase 1: Collect content before interrupt
                    if (foundConversationStart && !interrupted && isContentLine)
                    {
                        contentLinesBeforeInterrupt++;
                    }

                    // Phase 2: Wait for enough content, then interrupt
                    // Interrupt after 2 lines to maximize chance of catching stream while active
                    // (streams can complete very quickly, so we need to interrupt early)
                    if (foundConversationStart && !interrupted && contentLinesBeforeInterrupt >= 2)
                    {
                        this.OutputHelper.WriteLine($"Interrupting stream after {contentLinesBeforeInterrupt} content lines");
                        interrupted = true;
                        interruptTime = DateTime.Now;

                        // Send Enter to interrupt the stream
                        await this.WriteInputAsync(process, string.Empty, testTimeoutCts.Token);

                        // Give the cancellation token a moment to be processed
                        // Use a longer delay to ensure cancellation propagates
                        await Task.Delay(TimeSpan.FromMilliseconds(300), testTimeoutCts.Token);
                    }

                    // Phase 3: Look for "Last cursor" message after interrupt
                    if (interrupted && !resumed && line.Contains("Last cursor", StringComparison.OrdinalIgnoreCase))
                    {
                        foundLastCursor = true;

                        // Send Enter again to resume
                        this.OutputHelper.WriteLine("Resuming stream from last cursor");
                        await this.WriteInputAsync(process, string.Empty, testTimeoutCts.Token);
                        resumed = true;
                    }

                    // Phase 4: Look for resume message
                    if (resumed && line.Contains("Resuming conversation", StringComparison.OrdinalIgnoreCase))
                    {
                        foundResumeMessage = true;
                    }

                    // Phase 5: Collect content after resume
                    if (resumed && isContentLine)
                    {
                        contentLinesAfterResume++;
                    }

                    // Look for completion message - but don't break if we interrupted and haven't found Last cursor yet
                    // Allow some time after interrupt for the cancellation message to appear
                    if (line.Contains("Conversation completed", StringComparison.OrdinalIgnoreCase))
                    {
                        // If we interrupted but haven't found Last cursor, wait a bit more
                        if (interrupted && !foundLastCursor && interruptTime.HasValue)
                        {
                            TimeSpan timeSinceInterrupt = DateTime.Now - interruptTime.Value;
                            if (timeSinceInterrupt < TimeSpan.FromSeconds(2))
                            {
                                // Continue reading for a bit more to catch the cancellation message
                                this.OutputHelper.WriteLine("Stream completed naturally, but waiting for Last cursor message after interrupt...");
                                continue;
                            }
                        }

                        // Only break if we've completed the test or if stream completed without interruption
                        if (!interrupted || (resumed && foundResumeMessage && contentLinesAfterResume >= 5))
                        {
                            break;
                        }
                    }

                    // Stop once we've verified the interrupt/resume flow works
                    if (resumed && foundResumeMessage && contentLinesAfterResume >= 5)
                    {
                        this.OutputHelper.WriteLine($"Successfully verified interrupt/resume: {contentLinesBeforeInterrupt} lines before, {contentLinesAfterResume} lines after");
                        break;
                    }
                }

                // If we interrupted but didn't find Last cursor, wait a bit more for it to appear
                if (interrupted && !foundLastCursor && interruptTime.HasValue)
                {
                    TimeSpan timeSinceInterrupt = DateTime.Now - interruptTime.Value;
                    if (timeSinceInterrupt < TimeSpan.FromSeconds(3))
                    {
                        this.OutputHelper.WriteLine("Waiting for Last cursor message after interrupt...");
                        using CancellationTokenSource waitCts = new(TimeSpan.FromSeconds(2));
                        try
                        {
                            while ((line = this.ReadLogLine(logs, waitCts.Token)) != null)
                            {
                                if (line.Contains("Last cursor", StringComparison.OrdinalIgnoreCase))
                                {
                                    foundLastCursor = true;
                                    if (!resumed)
                                    {
                                        this.OutputHelper.WriteLine("Resuming stream from last cursor");
                                        await this.WriteInputAsync(process, string.Empty, testTimeoutCts.Token);
                                        resumed = true;
                                    }
                                    break;
                                }
                            }
                        }
                        catch (OperationCanceledException)
                        {
                            // Timeout waiting for Last cursor
                        }
                    }
                }
            }
            catch (OperationCanceledException)
            {
                // Timeout - check if we got enough to verify the flow
                this.OutputHelper.WriteLine($"Read timeout reached. Interrupted: {interrupted}, Resumed: {resumed}, Content before: {contentLinesBeforeInterrupt}, Content after: {contentLinesAfterResume}");
            }

            Assert.True(foundConversationStart, "Conversation start message not found.");
            Assert.True(contentLinesBeforeInterrupt >= 2, $"Not enough content before interrupt (got {contentLinesBeforeInterrupt}).");

            // If stream completed before interrupt could take effect, that's a timing issue
            // but we should still verify we got the conversation started
            if (!interrupted)
            {
                this.OutputHelper.WriteLine("WARNING: Stream completed before interrupt could be sent. This may indicate the stream is too fast.");
            }

            Assert.True(interrupted, "Stream was not interrupted (may have completed too quickly).");
            Assert.True(foundLastCursor, "'Last cursor' message not found after interrupt.");
            Assert.True(resumed, "Stream was not resumed.");
            Assert.True(foundResumeMessage, "Resume message not found.");
            Assert.True(contentLinesAfterResume > 0, "No content received after resume (expected to continue from cursor, not restart).");
        });
    }
}
