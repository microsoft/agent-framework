// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics;
using System.Reflection;
using System.Text;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

[Collection("Samples")]
[Trait("Category", "SampleValidation")]
public sealed class ConsoleAppSamplesValidation(ITestOutputHelper outputHelper) : IAsyncLifetime
{
    private const string DtsPort = "8080";
    private const string RedisPort = "6379";

    private static readonly string s_dotnetTargetFramework = GetTargetFramework();
    private static readonly IConfiguration s_configuration =
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private static bool s_infrastructureStarted;
    private static readonly string s_samplesPath = Path.GetFullPath(
        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", "..", "..", "samples", "04-hosting", "DurableAgents", "ConsoleApps"));

    private readonly ITestOutputHelper _outputHelper = outputHelper;

    async Task IAsyncLifetime.InitializeAsync()
    {
        if (!s_infrastructureStarted)
        {
            await this.StartSharedInfrastructureAsync();
            s_infrastructureStarted = true;
        }
    }

    async Task IAsyncLifetime.DisposeAsync()
    {
        // Nothing to clean up
        await Task.CompletedTask;
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
                        this._outputHelper.WriteLine($"Interrupting stream after {contentLinesBeforeInterrupt} content lines");
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
                        this._outputHelper.WriteLine("Resuming stream from last cursor");
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
                                this._outputHelper.WriteLine("Stream completed naturally, but waiting for Last cursor message after interrupt...");
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
                        this._outputHelper.WriteLine($"Successfully verified interrupt/resume: {contentLinesBeforeInterrupt} lines before, {contentLinesAfterResume} lines after");
                        break;
                    }
                }

                // If we interrupted but didn't find Last cursor, wait a bit more for it to appear
                if (interrupted && !foundLastCursor && interruptTime.HasValue)
                {
                    TimeSpan timeSinceInterrupt = DateTime.Now - interruptTime.Value;
                    if (timeSinceInterrupt < TimeSpan.FromSeconds(3))
                    {
                        this._outputHelper.WriteLine("Waiting for Last cursor message after interrupt...");
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
                                        this._outputHelper.WriteLine("Resuming stream from last cursor");
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
                this._outputHelper.WriteLine($"Read timeout reached. Interrupted: {interrupted}, Resumed: {resumed}, Content before: {contentLinesBeforeInterrupt}, Content after: {contentLinesAfterResume}");
            }

            Assert.True(foundConversationStart, "Conversation start message not found.");
            Assert.True(contentLinesBeforeInterrupt >= 2, $"Not enough content before interrupt (got {contentLinesBeforeInterrupt}).");

            // If stream completed before interrupt could take effect, that's a timing issue
            // but we should still verify we got the conversation started
            if (!interrupted)
            {
                this._outputHelper.WriteLine("WARNING: Stream completed before interrupt could be sent. This may indicate the stream is too fast.");
            }

            Assert.True(interrupted, "Stream was not interrupted (may have completed too quickly).");
            Assert.True(foundLastCursor, "'Last cursor' message not found after interrupt.");
            Assert.True(resumed, "Stream was not resumed.");
            Assert.True(foundResumeMessage, "Resume message not found.");
            Assert.True(contentLinesAfterResume > 0, "No content received after resume (expected to continue from cursor, not restart).");
        });
    }

    private static string GetTargetFramework()
    {
        string filePath = new Uri(typeof(ConsoleAppSamplesValidation).Assembly.Location).LocalPath;
        string directory = Path.GetDirectoryName(filePath)!;
        string tfm = Path.GetFileName(directory);
        if (tfm.StartsWith("net", StringComparison.OrdinalIgnoreCase))
        {
            return tfm;
        }

        throw new InvalidOperationException($"Unable to find target framework in path: {filePath}");
    }

    private async Task StartSharedInfrastructureAsync()
    {
        this._outputHelper.WriteLine("Starting shared infrastructure for console app samples...");

        // Start DTS emulator
        await this.StartDtsEmulatorAsync();

        // Start Redis
        await this.StartRedisAsync();

        // Wait for infrastructure to be ready
        await Task.Delay(TimeSpan.FromSeconds(5));
    }

    private async Task StartDtsEmulatorAsync()
    {
        // Start DTS emulator if it's not already running
        if (!await this.IsDtsEmulatorRunningAsync())
        {
            this._outputHelper.WriteLine("Starting DTS emulator...");
            await this.RunCommandAsync("docker", [
                "run", "-d",
                "--name", "dts-emulator",
                "-p", $"{DtsPort}:8080",
                "-e", "DTS_USE_DYNAMIC_TASK_HUBS=true",
                "mcr.microsoft.com/dts/dts-emulator:latest"
            ]);
        }
    }

    private async Task StartRedisAsync()
    {
        if (!await this.IsRedisRunningAsync())
        {
            this._outputHelper.WriteLine("Starting Redis...");
            await this.RunCommandAsync("docker", [
                "run", "-d",
                "--name", "redis",
                "-p", $"{RedisPort}:6379",
                "redis:latest"
            ]);
        }
    }

    private async Task<bool> IsDtsEmulatorRunningAsync()
    {
        this._outputHelper.WriteLine($"Checking if DTS emulator is running at http://localhost:{DtsPort}/healthz...");

        // DTS emulator doesn't support HTTP/1.1, so we need to use HTTP/2.0
        using HttpClient http2Client = new()
        {
            DefaultRequestVersion = new Version(2, 0),
            DefaultVersionPolicy = HttpVersionPolicy.RequestVersionExact
        };

        try
        {
            using CancellationTokenSource timeoutCts = new(TimeSpan.FromSeconds(30));
            using HttpResponseMessage response = await http2Client.GetAsync(new Uri($"http://localhost:{DtsPort}/healthz"), timeoutCts.Token);
            if (response.Content.Headers.ContentLength > 0)
            {
                string content = await response.Content.ReadAsStringAsync(timeoutCts.Token);
                this._outputHelper.WriteLine($"DTS emulator health check response: {content}");
            }

            if (response.IsSuccessStatusCode)
            {
                this._outputHelper.WriteLine("DTS emulator is running");
                return true;
            }

            this._outputHelper.WriteLine($"DTS emulator is not running. Status code: {response.StatusCode}");
            return false;
        }
        catch (HttpRequestException ex)
        {
            this._outputHelper.WriteLine($"DTS emulator is not running: {ex.Message}");
            return false;
        }
    }

    private async Task<bool> IsRedisRunningAsync()
    {
        this._outputHelper.WriteLine($"Checking if Redis is running at localhost:{RedisPort}...");

        try
        {
            using CancellationTokenSource timeoutCts = new(TimeSpan.FromSeconds(30));
            ProcessStartInfo startInfo = new()
            {
                FileName = "docker",
                Arguments = "exec redis redis-cli ping",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            using Process process = new() { StartInfo = startInfo };
            if (!process.Start())
            {
                this._outputHelper.WriteLine("Failed to start docker exec command");
                return false;
            }

            string output = await process.StandardOutput.ReadToEndAsync(timeoutCts.Token);
            await process.WaitForExitAsync(timeoutCts.Token);

            if (process.ExitCode == 0 && output.Contains("PONG", StringComparison.OrdinalIgnoreCase))
            {
                this._outputHelper.WriteLine("Redis is running");
                return true;
            }

            this._outputHelper.WriteLine($"Redis is not running. Exit code: {process.ExitCode}, Output: {output}");
            return false;
        }
        catch (Exception ex)
        {
            this._outputHelper.WriteLine($"Redis is not running: {ex.Message}");
            return false;
        }
    }

    private async Task RunSampleTestAsync(string samplePath, Func<Process, BlockingCollection<OutputLog>, Task> testAction)
    {
        // Generate a unique TaskHub name for this sample test to prevent cross-test interference
        // when multiple tests run together and share the same DTS emulator.
        string uniqueTaskHubName = $"sample-{Guid.NewGuid().ToString("N").Substring(0, 6)}";

        // Start the console app
        // Use BlockingCollection to safely read logs asynchronously captured from the process
        using BlockingCollection<OutputLog> logsContainer = [];
        using Process appProcess = this.StartConsoleApp(samplePath, logsContainer, uniqueTaskHubName);
        try
        {
            // Run the test
            await testAction(appProcess, logsContainer);
        }
        catch (OperationCanceledException e)
        {
            throw new TimeoutException("Core test logic timed out!", e);
        }
        finally
        {
            logsContainer.CompleteAdding();
            await this.StopProcessAsync(appProcess);
        }
    }

    private sealed record OutputLog(DateTime Timestamp, LogLevel Level, string Message);

    /// <summary>
    /// Writes a line to the process's stdin and flushes it.
    /// Logs the input being sent for debugging purposes.
    /// </summary>
    private async Task WriteInputAsync(Process process, string input, CancellationToken cancellationToken)
    {
        this._outputHelper.WriteLine($"{DateTime.Now:HH:mm:ss.fff} [{process.ProcessName}(in)]: {input}");
        await process.StandardInput.WriteLineAsync(input);
        await process.StandardInput.FlushAsync(cancellationToken);
    }

    /// <summary>
    /// Reads a line from the logs queue, filtering for Information level logs (stdout).
    /// Returns null if the collection is completed and empty, or if cancellation is requested.
    /// </summary>
    private string? ReadLogLine(BlockingCollection<OutputLog> logs, CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                // Block until a log entry is available or cancellation is requested
                // Take will throw OperationCanceledException if cancelled, or InvalidOperationException if collection is completed
                OutputLog log = logs.Take(cancellationToken);

                // Check for unhandled exceptions in the logs, which are never expected (but can happen)
                if (log.Message.Contains("Unhandled exception"))
                {
                    Assert.Fail("Console app encountered an unhandled exception.");
                }

                // Only return Information level logs (stdout), skip Error logs (stderr)
                if (log.Level == LogLevel.Information)
                {
                    return log.Message;
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Cancellation requested
            return null;
        }
        catch (InvalidOperationException)
        {
            // Collection is completed and empty
            return null;
        }

        return null;
    }

    private Process StartConsoleApp(string samplePath, BlockingCollection<OutputLog> logs, string taskHubName)
    {
        ProcessStartInfo startInfo = new()
        {
            FileName = "dotnet",
            Arguments = $"run --framework {s_dotnetTargetFramework}",
            WorkingDirectory = samplePath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
        };

        string openAiEndpoint = s_configuration["AZURE_OPENAI_ENDPOINT"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_ENDPOINT env variable is not set.");
        string openAiDeployment = s_configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_DEPLOYMENT_NAME env variable is not set.");

        void SetAndLogEnvironmentVariable(string key, string value)
        {
            this._outputHelper.WriteLine($"Setting environment variable for {startInfo.FileName} sub-process: {key}={value}");
            startInfo.EnvironmentVariables[key] = value;
        }

        // Set required environment variables for the app
        SetAndLogEnvironmentVariable("AZURE_OPENAI_ENDPOINT", openAiEndpoint);
        SetAndLogEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME", openAiDeployment);
        SetAndLogEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING",
            $"Endpoint=http://localhost:{DtsPort};TaskHub={taskHubName};Authentication=None");
        SetAndLogEnvironmentVariable("REDIS_CONNECTION_STRING", $"localhost:{RedisPort}");

        Process process = new() { StartInfo = startInfo };

        // Capture the output and error streams asynchronously
        // These events fire asynchronously, so we add to the blocking collection which is thread-safe
        process.ErrorDataReceived += (sender, e) =>
        {
            if (e.Data != null)
            {
                string logMessage = $"{DateTime.Now:HH:mm:ss.fff} [{startInfo.FileName}(err)]: {e.Data}";
                this._outputHelper.WriteLine(logMessage);
                Debug.WriteLine(logMessage);
                try
                {
                    logs.Add(new OutputLog(DateTime.Now, LogLevel.Error, e.Data));
                }
                catch (InvalidOperationException)
                {
                    // Collection is completed, ignore
                }
            }
        };

        process.OutputDataReceived += (sender, e) =>
        {
            if (e.Data != null)
            {
                string logMessage = $"{DateTime.Now:HH:mm:ss.fff} [{startInfo.FileName}(out)]: {e.Data}";
                this._outputHelper.WriteLine(logMessage);
                Debug.WriteLine(logMessage);
                try
                {
                    logs.Add(new OutputLog(DateTime.Now, LogLevel.Information, e.Data));
                }
                catch (InvalidOperationException)
                {
                    // Collection is completed, ignore
                }
            }
        };

        if (!process.Start())
        {
            throw new InvalidOperationException("Failed to start the console app");
        }

        process.BeginErrorReadLine();
        process.BeginOutputReadLine();

        return process;
    }

    private async Task RunCommandAsync(string command, string[] args)
    {
        await this.RunCommandAsync(command, workingDirectory: null, args: args);
    }

    private async Task RunCommandAsync(string command, string? workingDirectory, string[] args)
    {
        ProcessStartInfo startInfo = new()
        {
            FileName = command,
            Arguments = string.Join(" ", args),
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };

        this._outputHelper.WriteLine($"Running command: {command} {string.Join(" ", args)}");

        using Process process = new() { StartInfo = startInfo };
        process.ErrorDataReceived += (sender, e) => this._outputHelper.WriteLine($"[{command}(err)]: {e.Data}");
        process.OutputDataReceived += (sender, e) => this._outputHelper.WriteLine($"[{command}(out)]: {e.Data}");
        if (!process.Start())
        {
            throw new InvalidOperationException("Failed to start the command");
        }
        process.BeginErrorReadLine();
        process.BeginOutputReadLine();

        using CancellationTokenSource cancellationTokenSource = new(TimeSpan.FromMinutes(1));
        await process.WaitForExitAsync(cancellationTokenSource.Token);

        this._outputHelper.WriteLine($"Command completed with exit code: {process.ExitCode}");
    }

    private async Task StopProcessAsync(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                this._outputHelper.WriteLine($"{DateTime.Now:HH:mm:ss.fff} Killing process {process.ProcessName}#{process.Id}");
                process.Kill(entireProcessTree: true);

                using CancellationTokenSource timeoutCts = new(TimeSpan.FromSeconds(10));
                await process.WaitForExitAsync(timeoutCts.Token);
                this._outputHelper.WriteLine($"{DateTime.Now:HH:mm:ss.fff} Process exited: {process.Id}");
            }
        }
        catch (Exception ex)
        {
            this._outputHelper.WriteLine($"{DateTime.Now:HH:mm:ss.fff} Failed to stop process: {ex.Message}");
        }
    }

    private CancellationTokenSource CreateTestTimeoutCts(TimeSpan? timeout = null)
    {
        TimeSpan testTimeout = Debugger.IsAttached ? TimeSpan.FromMinutes(5) : timeout ?? TimeSpan.FromSeconds(60);
        return new CancellationTokenSource(testTimeout);
    }
}
