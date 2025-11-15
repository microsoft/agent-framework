// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.IntegrationTests;

[Collection("Samples")]
[Trait("Category", "SampleValidation")]
public sealed class SamplesValidation(ITestOutputHelper outputHelper) : IAsyncLifetime
{
    private const string AzureFunctionsPort = "7071";
    private const string AzuritePort = "10000";
    private const string DtsPort = "8080";

    private static readonly string s_dotnetTargetFramework = GetTargetFramework();
    private static readonly HttpClient s_sharedHttpClient = new();
    private static readonly IConfiguration s_configuration =
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private static bool s_infrastructureStarted;
    private static readonly TimeSpan s_orchestrationTimeout = TimeSpan.FromMinutes(1);
    private static readonly string s_samplesPath = Path.GetFullPath(
        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", "..", "..", "samples", "AzureFunctions"));

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
        string samplePath = Path.Combine(s_samplesPath, "01_SingleAgent");
        await this.RunSampleTestAsync(samplePath, async (logs) =>
        {
            Uri startUri = new($"http://localhost:{AzureFunctionsPort}/api/agents/Joker/run");
            this._outputHelper.WriteLine($"Starting single agent orchestration via POST request to {startUri}...");

            // Test the agent endpoint as described in the README
            const string RequestBody = "Tell me a joke about a pirate.";
            using HttpContent content = new StringContent(RequestBody, Encoding.UTF8, "text/plain");

            using HttpResponseMessage response = await s_sharedHttpClient.PostAsync(startUri, content);

            // The response is expected to be a plain text response with the agent's reply (the joke)
            Assert.True(response.IsSuccessStatusCode, $"Agent request failed with status: {response.StatusCode}");
            Assert.Equal("text/plain", response.Content.Headers.ContentType?.MediaType);
            string responseText = await response.Content.ReadAsStringAsync();
            Assert.NotEmpty(responseText);
            this._outputHelper.WriteLine($"Agent run response: {responseText}");

            // The response headers should include the agent thread ID, which can be used to continue the conversation.
            string? threadId = response.Headers.GetValues("x-ms-thread-id")?.FirstOrDefault();
            Assert.NotNull(threadId);

            this._outputHelper.WriteLine($"Agent thread ID: {threadId}");
            Assert.StartsWith("@dafx-joker@", threadId);

            // Wait for up to 30 seconds to see if the agent response is available in the logs
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        bool exists = logs.Any(
                            log => log.Message.Contains("Response:") && log.Message.Contains(threadId));
                        return Task.FromResult(exists);
                    }
                },
                message: "Agent response is available",
                timeout: TimeSpan.FromSeconds(30));
        });
    }

    [Fact]
    public async Task SingleAgentOrchestrationChainingSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "02_AgentOrchestration_Chaining");
        await this.RunSampleTestAsync(samplePath, async (logs) =>
        {
            Uri startUri = new($"http://localhost:{AzureFunctionsPort}/api/singleagent/run");
            this._outputHelper.WriteLine($"Starting single agent orchestration via POST request to {startUri}...");

            // Start the orchestration
            using HttpResponseMessage startResponse = await s_sharedHttpClient.PostAsync(startUri, content: null);

            Assert.True(
                startResponse.IsSuccessStatusCode,
                $"Start orchestration failed with status: {startResponse.StatusCode}");
            string startResponseText = await startResponse.Content.ReadAsStringAsync();
            JsonElement startResult = JsonSerializer.Deserialize<JsonElement>(startResponseText);

            Assert.True(startResult.TryGetProperty("statusQueryGetUri", out JsonElement statusUriElement));
            Uri statusUri = new(statusUriElement.GetString()!);

            // Wait for orchestration to complete
            await this.WaitForOrchestrationCompletionAsync(statusUri);

            // Verify the final result
            using HttpResponseMessage statusResponse = await s_sharedHttpClient.GetAsync(statusUri);
            Assert.True(
                statusResponse.IsSuccessStatusCode,
                $"Status check failed with status: {statusResponse.StatusCode}");

            string statusText = await statusResponse.Content.ReadAsStringAsync();
            JsonElement statusResult = JsonSerializer.Deserialize<JsonElement>(statusText);

            Assert.Equal("Completed", statusResult.GetProperty("runtimeStatus").GetString());
            Assert.True(statusResult.TryGetProperty("output", out JsonElement outputElement));
            string? output = outputElement.GetString();

            // Can't really validate the output since it's non-deterministic, but we can at least check it's non-empty
            Assert.NotNull(output);
            Assert.True(output.Length > 20, "Output is unexpectedly short");
        });
    }

    [Fact]
    public async Task MultiAgentOrchestrationConcurrentSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "03_AgentOrchestration_Concurrency");
        await this.RunSampleTestAsync(samplePath, async (logs) =>
        {
            // Start the multi-agent orchestration
            const string RequestBody = "What is temperature?";
            using HttpContent content = new StringContent(RequestBody, Encoding.UTF8, "text/plain");

            Uri startUri = new($"http://localhost:{AzureFunctionsPort}/api/multiagent/run");
            this._outputHelper.WriteLine($"Starting multi agent orchestration via POST request to {startUri}...");
            using HttpResponseMessage startResponse = await s_sharedHttpClient.PostAsync(startUri, content);

            Assert.True(startResponse.IsSuccessStatusCode, $"Start orchestration failed with status: {startResponse.StatusCode}");
            string startResponseText = await startResponse.Content.ReadAsStringAsync();
            JsonElement startResult = JsonSerializer.Deserialize<JsonElement>(startResponseText);

            Assert.True(startResult.TryGetProperty("instanceId", out JsonElement instanceIdElement));
            Assert.True(startResult.TryGetProperty("statusQueryGetUri", out JsonElement statusUriElement));

            Uri statusUri = new(statusUriElement.GetString()!);

            // Wait for orchestration to complete
            await this.WaitForOrchestrationCompletionAsync(statusUri);

            // Verify the final result
            using HttpResponseMessage statusResponse = await s_sharedHttpClient.GetAsync(statusUri);
            Assert.True(statusResponse.IsSuccessStatusCode, $"Status check failed with status: {statusResponse.StatusCode}");

            string statusText = await statusResponse.Content.ReadAsStringAsync();
            JsonElement statusResult = JsonSerializer.Deserialize<JsonElement>(statusText);

            Assert.Equal("Completed", statusResult.GetProperty("runtimeStatus").GetString());
            Assert.True(statusResult.TryGetProperty("output", out JsonElement outputElement));

            // Verify both physicist and chemist responses are present
            Assert.True(outputElement.TryGetProperty("physicist", out JsonElement physicistElement));
            Assert.True(outputElement.TryGetProperty("chemist", out JsonElement chemistElement));

            string physicistResponse = physicistElement.GetString()!;
            string chemistResponse = chemistElement.GetString()!;

            Assert.NotEmpty(physicistResponse);
            Assert.NotEmpty(chemistResponse);
            Assert.Contains("temperature", physicistResponse, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("temperature", chemistResponse, StringComparison.OrdinalIgnoreCase);
        });
    }

    [Fact]
    public async Task MultiAgentOrchestrationConditionalsSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "04_AgentOrchestration_Conditionals");
        await this.RunSampleTestAsync(samplePath, async (logs) =>
        {
            // Test with legitimate email
            await this.TestSpamDetectionAsync("email-001",
                "Hi John, I hope you're doing well. I wanted to follow up on our meeting yesterday about the quarterly report. Could you please send me the updated figures by Friday? Thanks!",
                expectedSpam: false);

            // Test with spam email
            await this.TestSpamDetectionAsync("email-002",
                "URGENT! You've won $1,000,000! Click here now to claim your prize! Limited time offer! Don't miss out!",
                expectedSpam: true);
        });
    }

    [Fact]
    public async Task SingleAgentOrchestrationHITLSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "05_AgentOrchestration_HITL");

        await this.RunSampleTestAsync(samplePath, async (logs) =>
        {
            // Start the HITL orchestration with short timeout for testing
            // TODO: Add validation for the approval case
            object requestBody = new
            {
                topic = "The Future of Artificial Intelligence",
                max_review_attempts = 3,
                approval_timeout_hours = 0.001 // Very short timeout for testing
            };

            string jsonContent = JsonSerializer.Serialize(requestBody);
            using HttpContent content = new StringContent(jsonContent, Encoding.UTF8, "application/json");

            Uri startUri = new($"http://localhost:{AzureFunctionsPort}/api/hitl/run");
            this._outputHelper.WriteLine($"Starting HITL orchestration via POST request to {startUri}...");
            using HttpResponseMessage startResponse = await s_sharedHttpClient.PostAsync(startUri, content);

            Assert.True(
                startResponse.IsSuccessStatusCode,
                $"Start HITL orchestration failed with status: {startResponse.StatusCode}");
            string startResponseText = await startResponse.Content.ReadAsStringAsync();
            JsonElement startResult = JsonSerializer.Deserialize<JsonElement>(startResponseText);

            Assert.True(startResult.TryGetProperty("statusQueryGetUri", out JsonElement statusUriElement));
            Uri statusUri = new(statusUriElement.GetString()!);

            // Wait for orchestration to complete (it should timeout due to short timeout)
            await this.WaitForOrchestrationCompletionAsync(statusUri);

            // Verify the final result
            using HttpResponseMessage statusResponse = await s_sharedHttpClient.GetAsync(statusUri);
            Assert.True(
                statusResponse.IsSuccessStatusCode,
                $"Status check failed with status: {statusResponse.StatusCode}");

            string statusText = await statusResponse.Content.ReadAsStringAsync();
            this._outputHelper.WriteLine($"HITL orchestration status text: {statusText}");

            JsonElement statusResult = JsonSerializer.Deserialize<JsonElement>(statusText);

            // The orchestration should complete with a failed status due to timeout
            Assert.Equal("Failed", statusResult.GetProperty("runtimeStatus").GetString());
            Assert.True(statusResult.TryGetProperty("failureDetails", out JsonElement failureDetailsElement));
            Assert.True(failureDetailsElement.TryGetProperty("ErrorType", out JsonElement errorTypeElement));
            Assert.Equal("System.TimeoutException", errorTypeElement.GetString());
            Assert.True(failureDetailsElement.TryGetProperty("ErrorMessage", out JsonElement errorMessageElement));
            Assert.StartsWith("Human approval timed out", errorMessageElement.GetString());
        });
    }

    [Fact]
    public async Task LongRunningToolsSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "06_LongRunningTools");

        await this.RunSampleTestAsync(samplePath, async (logs) =>
        {
            // Test starting an agent that schedules a content generation orchestration
            const string Prompt = "Start a content generation workflow for the topic 'The Future of Artificial Intelligence'";
            using HttpContent messageContent = new StringContent(Prompt, Encoding.UTF8, "text/plain");

            Uri runAgentUri = new($"http://localhost:{AzureFunctionsPort}/api/agents/publisher/run");

            this._outputHelper.WriteLine($"Starting agent tool orchestration via POST request to {runAgentUri}...");
            using HttpResponseMessage startResponse = await s_sharedHttpClient.PostAsync(runAgentUri, messageContent);

            Assert.True(
                startResponse.IsSuccessStatusCode,
                $"Start agent request failed with status: {startResponse.StatusCode}");

            string startResponseText = await startResponse.Content.ReadAsStringAsync();
            this._outputHelper.WriteLine($"Agent response: {startResponseText}");

            // The response should be deserializable as an AgentRunResponse object and have a valid thread ID
            startResponse.Headers.TryGetValues("x-ms-thread-id", out IEnumerable<string>? agentIdValues);
            string? threadId = agentIdValues?.FirstOrDefault();
            Assert.NotNull(threadId);
            Assert.StartsWith("@dafx-publisher@", threadId);

            // Wait for the orchestration to report that it's waiting for human approval
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    // For now, we have to rely on the logs to check for the "NOTIFICATION" message that gets generated by the activity function.
                    // TODO: Synchronously prompt the agent for status
                    lock (logs)
                    {
                        bool exists = logs.Any(log => log.Message.Contains("NOTIFICATION: Please review the following content for approval"));
                        return Task.FromResult(exists);
                    }
                },
                message: "Orchestration is requesting human feedback",
                timeout: TimeSpan.FromSeconds(60));

            // Approve the content
            Uri approvalUri = new($"{runAgentUri}?thread_id={threadId}");
            using HttpContent approvalContent = new StringContent("Approve the content", Encoding.UTF8, "text/plain");
            using HttpResponseMessage approvalResponse = await s_sharedHttpClient.PostAsync(approvalUri, approvalContent);
            Assert.True(approvalResponse.IsSuccessStatusCode, $"Approve content request failed with status: {approvalResponse.StatusCode}");

            // Wait for the publish notification to be logged
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        // TODO: Synchronously prompt the agent for status
                        bool exists = logs.Any(log => log.Message.Contains("PUBLISHING: Content has been published successfully"));
                        return Task.FromResult(exists);
                    }
                },
                message: "Content published notification is logged",
                timeout: TimeSpan.FromSeconds(60));

            // Verify the final orchestration status by asking the agent for the status
            Uri statusUri = new($"{runAgentUri}?thread_id={threadId}");
            await this.WaitForConditionAsync(
                condition: async () =>
                {
                    this._outputHelper.WriteLine($"Checking status of orchestration at {statusUri}...");

                    using StringContent content = new("Get the status of the workflow", Encoding.UTF8, "text/plain");
                    using HttpResponseMessage statusResponse = await s_sharedHttpClient.PostAsync(statusUri, content);
                    Assert.True(
                        statusResponse.IsSuccessStatusCode,
                        $"Status check failed with status: {statusResponse.StatusCode}");
                    string statusText = await statusResponse.Content.ReadAsStringAsync();
                    this._outputHelper.WriteLine($"Status text: {statusText}");

                    bool isCompleted = statusText.Contains("Completed", StringComparison.OrdinalIgnoreCase);
                    bool hasContent = statusText.Contains(
                        "The Future of Artificial Intelligence",
                        StringComparison.OrdinalIgnoreCase);
                    return isCompleted && hasContent;
                },
                message: "Orchestration is completed",
                timeout: TimeSpan.FromSeconds(60));
        });
    }

    [Fact]
    public async Task AgentAsMcpToolAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "07_AgentAsMcpTool");
        await this.RunSampleTestAsync(samplePath, async (logs) =>
        {
            IClientTransport clientTransport = new HttpClientTransport(new()
            {
                Endpoint = new Uri($"http://localhost:{AzureFunctionsPort}/runtime/webhooks/mcp")
            });

            await using McpClient mcpClient = await McpClient.CreateAsync(clientTransport!);

            // Ensure the expected tools are present.
            IList<McpClientTool> tools = await mcpClient.ListToolsAsync();

            Assert.Single(tools, t => t.Name == "StockAdvisor");
            Assert.Single(tools, t => t.Name == "PlantAdvisor");

            // Invoke the tools to verify they work as expected.
            string stockPriceResponse = await this.InvokeMcpToolAsync(mcpClient, "StockAdvisor", "MSFT ATH");
            string plantSuggestionResponse = await this.InvokeMcpToolAsync(mcpClient, "PlantAdvisor", "Low light plant");
            Assert.NotEmpty(stockPriceResponse);
            Assert.NotEmpty(plantSuggestionResponse);

            // Wait for up to 30 seconds to see if the agent responses are available in the logs
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        bool expectedLogsPresent = logs.Count(log => log.Message.Contains("Response:")) >= 2;
                        return Task.FromResult(expectedLogsPresent);
                    }
                },
                message: "Agent response is available",
                timeout: TimeSpan.FromSeconds(30));
        });
    }

    private async Task<string> InvokeMcpToolAsync(McpClient mcpClient, string toolName, string query)
    {
        this._outputHelper.WriteLine($"Invoking MCP tool '{toolName}'...");

        CallToolResult result = await mcpClient.CallToolAsync(
            toolName,
            arguments: new Dictionary<string, object?> { { "query", query } });

        string toolCallResult = ((TextContentBlock)result.Content[0]).Text;
        this._outputHelper.WriteLine($"MCP tool '{toolName}' response: {toolCallResult}");

        return toolCallResult;
    }

    private async Task TestSpamDetectionAsync(string emailId, string emailContent, bool expectedSpam)
    {
        object requestBody = new
        {
            email_id = emailId,
            email_content = emailContent
        };

        string jsonContent = JsonSerializer.Serialize(requestBody);
        using HttpContent content = new StringContent(jsonContent, Encoding.UTF8, "application/json");

        Uri startUri = new($"http://localhost:{AzureFunctionsPort}/api/spamdetection/run");
        this._outputHelper.WriteLine($"Starting spam detection orchestration via POST request to {startUri}...");
        using HttpResponseMessage startResponse = await s_sharedHttpClient.PostAsync(startUri, content);

        Assert.True(startResponse.IsSuccessStatusCode, $"Start orchestration failed with status: {startResponse.StatusCode}");
        string startResponseText = await startResponse.Content.ReadAsStringAsync();
        JsonElement startResult = JsonSerializer.Deserialize<JsonElement>(startResponseText);

        Assert.True(startResult.TryGetProperty("statusQueryGetUri", out JsonElement statusUriElement));
        Uri statusUri = new(statusUriElement.GetString()!);

        // Wait for orchestration to complete
        await this.WaitForOrchestrationCompletionAsync(statusUri);

        // Verify the final result
        using HttpResponseMessage statusResponse = await s_sharedHttpClient.GetAsync(statusUri);
        Assert.True(statusResponse.IsSuccessStatusCode, $"Status check failed with status: {statusResponse.StatusCode}");

        string statusText = await statusResponse.Content.ReadAsStringAsync();
        JsonElement statusResult = JsonSerializer.Deserialize<JsonElement>(statusText);

        Assert.Equal("Completed", statusResult.GetProperty("runtimeStatus").GetString());
        Assert.True(statusResult.TryGetProperty("output", out JsonElement outputElement));

        string output = outputElement.GetString()!;
        Assert.NotEmpty(output);

        if (expectedSpam)
        {
            Assert.Contains("spam", output, StringComparison.OrdinalIgnoreCase);
        }
        else
        {
            Assert.Contains("sent", output, StringComparison.OrdinalIgnoreCase);
        }
    }

    private async Task StartSharedInfrastructureAsync()
    {
        // Start Azurite if it's not already running
        if (!await this.IsAzuriteRunningAsync())
        {
            await this.StartDockerContainerAsync(
                containerName: "azurite",
                image: "mcr.microsoft.com/azure-storage/azurite",
                ports: ["-p", "10000:10000", "-p", "10001:10001", "-p", "10002:10002"]);

            // Wait for Azurite
            await this.WaitForConditionAsync(this.IsAzuriteRunningAsync, "Azurite is running", TimeSpan.FromSeconds(30));
        }

        // Start DTS emulator if it's not already running
        if (!await this.IsDtsEmulatorRunningAsync())
        {
            await this.StartDockerContainerAsync(
                containerName: "dts-emulator",
                image: "mcr.microsoft.com/dts/dts-emulator:latest",
                ports: ["-p", "8080:8080", "-p", "8082:8082"]);

            // Wait for DTS emulator
            await this.WaitForConditionAsync(
                condition: this.IsDtsEmulatorRunningAsync,
                message: "DTS emulator is running",
                timeout: TimeSpan.FromSeconds(30));
        }
    }

    private async Task<bool> IsAzuriteRunningAsync()
    {
        this._outputHelper.WriteLine(
            $"Checking if Azurite is running at http://localhost:{AzuritePort}/devstoreaccount1...");

        try
        {
            using CancellationTokenSource timeoutCts = new(TimeSpan.FromSeconds(30));

            // Example output when pinging Azurite:
            // $ curl -i http://localhost:10000/devstoreaccount1?comp=list
            // HTTP/1.1 403 Server failed to authenticate the request.
            // Server: Azurite-Blob/3.34.0
            // x-ms-error-code: AuthorizationFailure
            // x-ms-request-id: 6cd21522-bb0f-40f6-962c-fa174f17aa30
            // content-type: application/xml
            // Date: Mon, 20 Oct 2025 23:52:02 GMT
            // Connection: keep-alive
            // Keep-Alive: timeout=5
            // Transfer-Encoding: chunked
            using HttpResponseMessage response = await s_sharedHttpClient.GetAsync(
                requestUri: new Uri($"http://localhost:{AzuritePort}/devstoreaccount1?comp=list"),
                cancellationToken: timeoutCts.Token);
            if (response.Headers.TryGetValues(
                "Server",
                out IEnumerable<string>? serverValues) && serverValues.Any(s => s.StartsWith("Azurite", StringComparison.OrdinalIgnoreCase)))
            {
                this._outputHelper.WriteLine($"Azurite is running, server: {string.Join(", ", serverValues)}");
                return true;
            }

            this._outputHelper.WriteLine($"Azurite is not running. Status code: {response.StatusCode}");
            return false;
        }
        catch (HttpRequestException ex)
        {
            this._outputHelper.WriteLine($"Azurite is not running: {ex.Message}");
            return false;
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

    private async Task StartDockerContainerAsync(string containerName, string image, string[] ports)
    {
        // Stop existing container if it exists
        await this.RunCommandAsync("docker", ["stop", containerName]);
        await this.RunCommandAsync("docker", ["rm", containerName]);

        // Start new container
        List<string> args = ["run", "-d", "--name", containerName];
        args.AddRange(ports);
        args.Add(image);

        this._outputHelper.WriteLine(
            $"Starting new container: {containerName} with image: {image} and ports: {string.Join(", ", ports)}");
        await this.RunCommandAsync("docker", args.ToArray());
        this._outputHelper.WriteLine($"Container started: {containerName}");
    }

    private async Task WaitForConditionAsync(Func<Task<bool>> condition, string message, TimeSpan timeout)
    {
        this._outputHelper.WriteLine($"Waiting for '{message}'...");

        using CancellationTokenSource cancellationTokenSource = new(timeout);
        while (true)
        {
            if (await condition())
            {
                return;
            }

            try
            {
                await Task.Delay(TimeSpan.FromSeconds(1), cancellationTokenSource.Token);
            }
            catch (OperationCanceledException) when (cancellationTokenSource.IsCancellationRequested)
            {
                throw new TimeoutException($"Timeout waiting for '{message}'");
            }
        }
    }

    private async Task RunSampleTestAsync(string samplePath, Func<IReadOnlyList<OutputLog>, Task> testAction)
    {
        // Start the Azure Functions app
        List<OutputLog> logsContainer = [];
        using Process funcProcess = this.StartFunctionApp(samplePath, logsContainer);
        try
        {
            // Wait for the app to be ready
            await this.WaitForAzureFunctionsAsync();

            // Run the test
            await testAction(logsContainer);
        }
        finally
        {
            await this.StopProcessAsync(funcProcess);
        }
    }

    private sealed record OutputLog(DateTime Timestamp, LogLevel Level, string Message);

    private Process StartFunctionApp(string samplePath, List<OutputLog> logs)
    {
        ProcessStartInfo startInfo = new()
        {
            FileName = "dotnet",
            Arguments = $"run -f {s_dotnetTargetFramework} --port {AzureFunctionsPort}",
            WorkingDirectory = samplePath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        string openAiEndpoint = s_configuration["AZURE_OPENAI_ENDPOINT"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_ENDPOINT env variable is not set.");
        string openAiDeployment = s_configuration["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_CHAT_DEPLOYMENT_NAME env variable is not set.");

        // Set required environment variables for the function app (see local.settings.json for required settings)
        startInfo.EnvironmentVariables["AZURE_OPENAI_ENDPOINT"] = openAiEndpoint;
        startInfo.EnvironmentVariables["AZURE_OPENAI_DEPLOYMENT"] = openAiDeployment;
        startInfo.EnvironmentVariables["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"] =
            $"Endpoint=http://localhost:{DtsPort};TaskHub=default;Authentication=None";
        startInfo.EnvironmentVariables["AzureWebJobsStorage"] = "UseDevelopmentStorage=true";

        Process process = new() { StartInfo = startInfo };

        // Capture the output and error streams
        process.ErrorDataReceived += (sender, e) =>
        {
            if (e.Data != null)
            {
                this._outputHelper.WriteLine($"[{startInfo.FileName}(err)]: {e.Data}");
                lock (logs)
                {
                    logs.Add(new OutputLog(DateTime.Now, LogLevel.Error, e.Data));
                }
            }
        };

        process.OutputDataReceived += (sender, e) =>
        {
            if (e.Data != null)
            {
                this._outputHelper.WriteLine($"[{startInfo.FileName}(out)]: {e.Data}");
                lock (logs)
                {
                    logs.Add(new OutputLog(DateTime.Now, LogLevel.Information, e.Data));
                }
            }
        };

        if (!process.Start())
        {
            throw new InvalidOperationException("Failed to start the function app");
        }

        process.BeginErrorReadLine();
        process.BeginOutputReadLine();

        return process;
    }

    private async Task WaitForAzureFunctionsAsync()
    {
        this._outputHelper.WriteLine(
            $"Waiting for Azure Functions Core Tools to be ready at http://localhost:{AzureFunctionsPort}/...");
        await this.WaitForConditionAsync(
            condition: async () =>
            {
                try
                {
                    using HttpRequestMessage request = new(HttpMethod.Head, $"http://localhost:{AzureFunctionsPort}/");
                    using HttpResponseMessage response = await s_sharedHttpClient.SendAsync(request);
                    this._outputHelper.WriteLine($"Azure Functions Core Tools response: {response.StatusCode}");
                    return response.IsSuccessStatusCode;
                }
                catch (HttpRequestException)
                {
                    // Expected when the app isn't yet ready
                    return false;
                }
            },
            message: "Azure Functions Core Tools is ready",
            timeout: TimeSpan.FromSeconds(60));
    }

    private async Task WaitForOrchestrationCompletionAsync(Uri statusUri)
    {
        using CancellationTokenSource timeoutCts = new(s_orchestrationTimeout);
        while (true)
        {
            try
            {
                using HttpResponseMessage response = await s_sharedHttpClient.GetAsync(
                    statusUri,
                    timeoutCts.Token);
                if (response.IsSuccessStatusCode)
                {
                    string responseText = await response.Content.ReadAsStringAsync(timeoutCts.Token);
                    JsonElement result = JsonSerializer.Deserialize<JsonElement>(responseText);

                    if (result.TryGetProperty("runtimeStatus", out JsonElement statusElement))
                    {
                        string status = statusElement.GetString()!;
                        if (status == "Completed" || status == "Failed" || status == "Terminated")
                        {
                            return;
                        }
                    }
                }
            }
            catch (Exception ex) when (!timeoutCts.Token.IsCancellationRequested)
            {
                // Ignore errors and retry
                this._outputHelper.WriteLine($"Error waiting for orchestration completion: {ex}");
            }

            await Task.Delay(TimeSpan.FromSeconds(1), timeoutCts.Token);
        }
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
                this._outputHelper.WriteLine($"Killing process {process.ProcessName}#{process.Id}");
                process.Kill(entireProcessTree: true);

                using CancellationTokenSource timeoutCts = new(TimeSpan.FromSeconds(10));
                await process.WaitForExitAsync(timeoutCts.Token);
                this._outputHelper.WriteLine($"Process exited: {process.Id}");
            }
        }
        catch (Exception ex)
        {
            this._outputHelper.WriteLine($"Failed to stop process: {ex.Message}");
        }
    }

    private static string GetTargetFramework()
    {
        // Get the target framework by looking at the path of the current file. It should be something like /path/to/project/bin/Debug/net8.0/...
        string filePath = new Uri(typeof(SamplesValidation).Assembly.Location).LocalPath;
        string directory = Path.GetDirectoryName(filePath)!;
        string tfm = Path.GetFileName(directory);
        if (tfm.StartsWith("net", StringComparison.OrdinalIgnoreCase))
        {
            return tfm;
        }

        throw new InvalidOperationException($"Unable to find target framework in path: {filePath}");
    }
}
