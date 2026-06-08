// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
namespace Microsoft.Agents.AI.Hosting.AzureFunctions.IntegrationTests;

/// <summary>
/// Integration tests for validating the durable workflow Azure Functions samples
/// located in samples/04-hosting/DurableWorkflows/AzureFunctions.
/// </summary>
[Collection("Samples")]
[Trait("Category", "SampleValidation")]
public sealed class WorkflowSamplesValidation(ITestOutputHelper outputHelper) : IAsyncLifetime
{
    private const string AzureFunctionsPort = "7071";
    private const string AzuritePort = "10000";
    private const string DtsPort = "8080";

    private static readonly string s_dotnetTargetFramework = GetTargetFramework();

#if DEBUG
    private const string BuildConfiguration = "Debug";
#else
    private const string BuildConfiguration = "Release";
#endif
    private static readonly HttpClient s_sharedHttpClient = new();
    private static readonly IConfiguration s_configuration =
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private static bool s_infrastructureStarted;
    private static readonly TimeSpan s_orchestrationTimeout = TimeSpan.FromMinutes(1);

    // Timeout for the Azure Functions host to become ready after building.
    private static readonly TimeSpan s_functionsReadyTimeout = TimeSpan.FromSeconds(180);

    private static readonly string s_samplesPath = Path.GetFullPath(
        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", "..", "..", "samples", "04-hosting", "DurableWorkflows", "AzureFunctions"));

    private readonly ITestOutputHelper _outputHelper = outputHelper;

    public async ValueTask InitializeAsync()
    {
        if (!s_infrastructureStarted)
        {
            await this.StartSharedInfrastructureAsync();
            s_infrastructureStarted = true;
        }
    }

    public ValueTask DisposeAsync()
    {
        GC.SuppressFinalize(this);
        return default;
    }

    [Fact]
    public async Task SequentialWorkflowSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "01_SequentialWorkflow");
        await this.RunSampleTestAsync(samplePath, requiresOpenAI: false, async (logs) =>
        {
            // Test the CancelOrder workflow
            Uri cancelOrderUri = new($"http://localhost:{AzureFunctionsPort}/api/workflows/CancelOrder/run");
            this._outputHelper.WriteLine($"Starting CancelOrder workflow via POST request to {cancelOrderUri}...");

            using HttpContent cancelContent = new StringContent("12345", Encoding.UTF8, "text/plain");
            using HttpResponseMessage cancelResponse = await s_sharedHttpClient.PostAsync(cancelOrderUri, cancelContent);

            Assert.True(cancelResponse.IsSuccessStatusCode, $"CancelOrder request failed with status: {cancelResponse.StatusCode}");
            string cancelResponseText = await cancelResponse.Content.ReadAsStringAsync();
            Assert.Contains("CancelOrder", cancelResponseText);
            this._outputHelper.WriteLine($"CancelOrder response: {cancelResponseText}");

            // Wait for the CancelOrder workflow to complete by checking logs
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        bool exists = logs.Any(log => log.Message.Contains("Workflow completed"));
                        return Task.FromResult(exists);
                    }
                },
                message: "CancelOrder workflow completed",
                timeout: s_orchestrationTimeout);

            // Verify the executor activities ran in sequence
            lock (logs)
            {
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] OrderLookup:")), "OrderLookup activity not found in logs.");
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] OrderCancel:")), "OrderCancel activity not found in logs.");
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] SendEmail:")), "SendEmail activity not found in logs.");
            }

            // Test the OrderStatus workflow (shares OrderLookup executor with CancelOrder)
            Uri orderStatusUri = new($"http://localhost:{AzureFunctionsPort}/api/workflows/OrderStatus/run");
            this._outputHelper.WriteLine($"Starting OrderStatus workflow via POST request to {orderStatusUri}...");

            using HttpContent statusContent = new StringContent("67890", Encoding.UTF8, "text/plain");
            using HttpResponseMessage statusResponse = await s_sharedHttpClient.PostAsync(orderStatusUri, statusContent);

            Assert.True(statusResponse.IsSuccessStatusCode, $"OrderStatus request failed with status: {statusResponse.StatusCode}");
            string statusResponseText = await statusResponse.Content.ReadAsStringAsync();
            Assert.Contains("OrderStatus", statusResponseText);
            this._outputHelper.WriteLine($"OrderStatus response: {statusResponseText}");

            // Wait for the OrderStatus workflow to complete
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        // Look for StatusReport activity which is unique to OrderStatus workflow
                        bool exists = logs.Any(log => log.Message.Contains("[Activity] StatusReport:"));
                        return Task.FromResult(exists);
                    }
                },
                message: "OrderStatus workflow completed",
                timeout: s_orchestrationTimeout);

            // Test the CancelOrder workflow with x-ms-wait-for-response header
            this._outputHelper.WriteLine("Starting CancelOrder workflow with x-ms-wait-for-response: true...");

            using HttpRequestMessage waitRequest = new(HttpMethod.Post, cancelOrderUri);
            waitRequest.Content = new StringContent("55555", Encoding.UTF8, "text/plain");
            waitRequest.Headers.Add("x-ms-wait-for-response", "true");
            using HttpResponseMessage waitResponse = await s_sharedHttpClient.SendAsync(waitRequest);

            Assert.True(waitResponse.IsSuccessStatusCode, $"CancelOrder wait-for-response request failed with status: {waitResponse.StatusCode}");
            string waitResponseText = await waitResponse.Content.ReadAsStringAsync();
            this._outputHelper.WriteLine($"CancelOrder wait-for-response result: {waitResponseText}");

            // The response should contain the workflow result (not just "started for CancelOrder")
            Assert.DoesNotContain("Workflow orchestration started", waitResponseText);
            Assert.Contains("55555", waitResponseText);

            // Test the wait-for-response with Accept: application/json header
            this._outputHelper.WriteLine("Starting CancelOrder workflow with x-ms-wait-for-response and Accept: application/json...");

            using HttpRequestMessage jsonWaitRequest = new(HttpMethod.Post, cancelOrderUri);
            jsonWaitRequest.Content = new StringContent("77777", Encoding.UTF8, "text/plain");
            jsonWaitRequest.Headers.Add("x-ms-wait-for-response", "true");
            jsonWaitRequest.Headers.Add("Accept", "application/json");

            using CancellationTokenSource jsonWaitCts = new(s_orchestrationTimeout);
            using HttpResponseMessage jsonWaitResponse = await s_sharedHttpClient.SendAsync(jsonWaitRequest, jsonWaitCts.Token);

            Assert.True(jsonWaitResponse.IsSuccessStatusCode, $"CancelOrder JSON wait-for-response request failed with status: {jsonWaitResponse.StatusCode}");
            string jsonWaitResponseText = await jsonWaitResponse.Content.ReadAsStringAsync();
            this._outputHelper.WriteLine($"CancelOrder JSON wait-for-response result: {jsonWaitResponseText}");

            using JsonDocument jsonDoc = JsonDocument.Parse(jsonWaitResponseText);
            JsonElement root = jsonDoc.RootElement;
            Assert.True(root.TryGetProperty("runId", out _), "JSON response missing 'runId' property");
            Assert.True(root.TryGetProperty("workflowStatus", out JsonElement statusEl), "JSON response missing 'workflowStatus' property");
            Assert.Equal("Completed", statusEl.GetString());
            Assert.True(root.TryGetProperty("result", out JsonElement resultEl), "JSON response missing 'result' property");
            Assert.Contains("77777", resultEl.GetString());
        });
    }

    [Fact]
    public async Task HITLWorkflowSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "03_WorkflowHITL");
        await this.RunSampleTestAsync(samplePath, requiresOpenAI: false, async (logs) =>
        {
            // Use a unique run ID to avoid conflicts with previous test runs
            string runId = $"hitl-test-{Guid.NewGuid():N}";

            // Step 1: Start the expense reimbursement workflow
            Uri runUri = new($"http://localhost:{AzureFunctionsPort}/api/workflows/ExpenseReimbursement/run?runId={runId}");
            this._outputHelper.WriteLine($"Starting ExpenseReimbursement workflow via POST request to {runUri}...");

            using HttpContent runContent = new StringContent("EXP-2025-001", Encoding.UTF8, "text/plain");
            using HttpResponseMessage runResponse = await s_sharedHttpClient.PostAsync(runUri, runContent);

            Assert.True(runResponse.IsSuccessStatusCode, $"Run request failed with status: {runResponse.StatusCode}");
            string runResponseText = await runResponse.Content.ReadAsStringAsync();
            Assert.Contains("ExpenseReimbursement", runResponseText);
            this._outputHelper.WriteLine($"Run response: {runResponseText}");

            // Step 2: Wait for the workflow to pause at the ManagerApproval RequestPort
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        bool exists = logs.Any(log => log.Message.Contains("Workflow waiting for external input at RequestPort 'ManagerApproval'"));
                        return Task.FromResult(exists);
                    }
                },
                message: "Workflow paused at ManagerApproval RequestPort",
                timeout: s_orchestrationTimeout);

            // Step 3: Send approval response to resume the workflow
            Uri respondUri = new($"http://localhost:{AzureFunctionsPort}/api/workflows/ExpenseReimbursement/respond/{runId}");
            this._outputHelper.WriteLine($"Sending approval response via POST request to {respondUri}...");

            using HttpContent respondContent = new StringContent(
                """{"eventName": "ManagerApproval", "response": {"Approved": true, "Comments": "Approved by test."}}""",
                Encoding.UTF8, "application/json");
            using HttpResponseMessage respondResponse = await s_sharedHttpClient.PostAsync(respondUri, respondContent);

            Assert.True(respondResponse.IsSuccessStatusCode, $"Respond request failed with status: {respondResponse.StatusCode}");
            string respondResponseText = await respondResponse.Content.ReadAsStringAsync();
            Assert.Contains("Response sent to workflow", respondResponseText);
            this._outputHelper.WriteLine($"Respond response: {respondResponseText}");

            // Step 4: Wait for the workflow to pause at the parallel BudgetApproval and ComplianceApproval RequestPorts
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        bool exists = logs.Any(log => log.Message.Contains("Workflow waiting for external input at RequestPort 'BudgetApproval'"));
                        return Task.FromResult(exists);
                    }
                },
                message: "Workflow paused at BudgetApproval RequestPort",
                timeout: s_orchestrationTimeout);

            // Step 5a: Send budget approval response
            this._outputHelper.WriteLine("Sending BudgetApproval response...");

            using HttpContent budgetContent = new StringContent(
                """{"eventName": "BudgetApproval", "response": {"Approved": true, "Comments": "Budget approved by test."}}""",
                Encoding.UTF8, "application/json");
            using HttpResponseMessage budgetResponse = await s_sharedHttpClient.PostAsync(respondUri, budgetContent);

            Assert.True(budgetResponse.IsSuccessStatusCode, $"BudgetApproval request failed with status: {budgetResponse.StatusCode}");
            this._outputHelper.WriteLine($"BudgetApproval response: {await budgetResponse.Content.ReadAsStringAsync()}");

            // Step 5b: Send compliance approval response
            this._outputHelper.WriteLine("Sending ComplianceApproval response...");

            using HttpContent complianceContent = new StringContent(
                """{"eventName": "ComplianceApproval", "response": {"Approved": true, "Comments": "Compliance approved by test."}}""",
                Encoding.UTF8, "application/json");
            using HttpResponseMessage complianceResponse = await s_sharedHttpClient.PostAsync(respondUri, complianceContent);

            Assert.True(complianceResponse.IsSuccessStatusCode, $"ComplianceApproval request failed with status: {complianceResponse.StatusCode}");
            this._outputHelper.WriteLine($"ComplianceApproval response: {await complianceResponse.Content.ReadAsStringAsync()}");

            // Step 6: Wait for the workflow to complete
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        bool exists = logs.Any(log => log.Message.Contains("Workflow completed"));
                        return Task.FromResult(exists);
                    }
                },
                message: "HITL workflow completed",
                timeout: s_orchestrationTimeout);

            // Verify executor activities ran
            lock (logs)
            {
                Assert.True(logs.Any(log => log.Message.Contains("Received external event for RequestPort 'ManagerApproval'")),
                    "ManagerApproval external event receipt not found in logs.");
                Assert.True(logs.Any(log => log.Message.Contains("Received external event for RequestPort 'BudgetApproval'")),
                    "BudgetApproval external event receipt not found in logs.");
                Assert.True(logs.Any(log => log.Message.Contains("Received external event for RequestPort 'ComplianceApproval'")),
                    "ComplianceApproval external event receipt not found in logs.");
            }
        });
    }

    [Fact]
    public async Task WorkflowMcpToolSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "04_WorkflowMcpTool");
        await this.RunSampleTestAsync(samplePath, requiresOpenAI: false, async (logs) =>
        {
            // Connect to the MCP endpoint exposed by the Azure Functions host
            IClientTransport clientTransport = new HttpClientTransport(new()
            {
                Endpoint = new Uri($"http://localhost:{AzureFunctionsPort}/runtime/webhooks/mcp")
            });

            await using McpClient mcpClient = await McpClient.CreateAsync(clientTransport);

            // Verify both workflow tools are listed
            IList<McpClientTool> tools = await mcpClient.ListToolsAsync();
            this._outputHelper.WriteLine($"MCP tools found: {string.Join(", ", tools.Select(t => t.Name))}");

            Assert.Single(tools, t => t.Name == "Translate");
            Assert.Single(tools, t => t.Name == "OrderLookup");

            // Invoke the Translate workflow via MCP tool (returns a string result)
            this._outputHelper.WriteLine("Invoking MCP tool 'Translate'...");
            CallToolResult translateResult = await mcpClient.CallToolAsync(
                "Translate",
                arguments: new Dictionary<string, object?> { { "input", "hello world" } });

            Assert.NotEmpty(translateResult.Content);
            string translateResponse = Assert.IsType<TextContentBlock>(translateResult.Content[0]).Text;
            this._outputHelper.WriteLine($"Translate MCP tool response: {translateResponse}");
            Assert.NotEmpty(translateResponse);
            Assert.Contains("HELLO WORLD", translateResponse);

            // Invoke the OrderLookup workflow via MCP tool (returns a POCO serialized as JSON)
            this._outputHelper.WriteLine("Invoking MCP tool 'OrderLookup'...");
            CallToolResult orderResult = await mcpClient.CallToolAsync(
                "OrderLookup",
                arguments: new Dictionary<string, object?> { { "input", "ORD-2025-42" } });

            Assert.NotEmpty(orderResult.Content);
            string orderResponse = Assert.IsType<TextContentBlock>(orderResult.Content[0]).Text;
            this._outputHelper.WriteLine($"OrderLookup MCP tool response: {orderResponse}");
            Assert.NotEmpty(orderResponse);
            Assert.Contains("ORD-2025-42", orderResponse);

            // Verify executor activities ran in the logs
            lock (logs)
            {
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] TranslateText:")), "TranslateText activity not found in logs.");
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] FormatOutput:")), "FormatOutput activity not found in logs.");
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] LookupOrder:")), "LookupOrder activity not found in logs.");
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] EnrichOrder:")), "EnrichOrder activity not found in logs.");
            }
        });
    }

    [Fact]
    public async Task WorkflowAndAgentsSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "05_WorkflowAndAgents");
        await this.RunSampleTestAsync(samplePath, requiresOpenAI: true, async (logs) =>
        {
            // Connect to the MCP endpoint exposed by the Azure Functions host
            IClientTransport clientTransport = new HttpClientTransport(new()
            {
                Endpoint = new Uri($"http://localhost:{AzureFunctionsPort}/runtime/webhooks/mcp")
            });

            await using McpClient mcpClient = await McpClient.CreateAsync(clientTransport);

            // Verify both the agent and workflow tools are listed
            IList<McpClientTool> tools = await mcpClient.ListToolsAsync();
            this._outputHelper.WriteLine($"MCP tools found: {string.Join(", ", tools.Select(t => t.Name))}");

            Assert.Single(tools, t => t.Name == "Assistant");
            Assert.Single(tools, t => t.Name == "Translate");

            // Invoke the Translate workflow via MCP tool
            this._outputHelper.WriteLine("Invoking MCP tool 'Translate'...");
            CallToolResult translateResult = await mcpClient.CallToolAsync(
                "Translate",
                arguments: new Dictionary<string, object?> { { "input", "hello world" } });

            Assert.NotEmpty(translateResult.Content);
            string translateResponse = Assert.IsType<TextContentBlock>(translateResult.Content[0]).Text;
            this._outputHelper.WriteLine($"Translate MCP tool response: {translateResponse}");
            Assert.Contains("HELLO WORLD", translateResponse);

            // Invoke the Assistant agent via MCP tool
            this._outputHelper.WriteLine("Invoking MCP tool 'Assistant'...");
            CallToolResult assistantResult = await mcpClient.CallToolAsync(
                "Assistant",
                arguments: new Dictionary<string, object?> { { "query", "What is 2 + 2?" } });

            Assert.NotEmpty(assistantResult.Content);
            string assistantResponse = Assert.IsType<TextContentBlock>(assistantResult.Content[0]).Text;
            this._outputHelper.WriteLine($"Assistant MCP tool response: {assistantResponse}");
            Assert.NotEmpty(assistantResponse);

            // Verify workflow executor activities ran in the logs
            lock (logs)
            {
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] TranslateText:")), "TranslateText activity not found in logs.");
                Assert.True(logs.Any(log => log.Message.Contains("[Activity] FormatOutput:")), "FormatOutput activity not found in logs.");
            }
        });
    }

    [Fact]
    public async Task ConcurrentWorkflowSampleValidationAsync()
    {
        string samplePath = Path.Combine(s_samplesPath, "02_ConcurrentWorkflow");
        await this.RunSampleTestAsync(samplePath, requiresOpenAI: true, async (logs) =>
        {
            // Start the ExpertReview workflow with a science question
            const string RequestBody = "What is temperature?";
            using HttpContent content = new StringContent(RequestBody, Encoding.UTF8, "text/plain");

            Uri startUri = new($"http://localhost:{AzureFunctionsPort}/api/workflows/ExpertReview/run");
            this._outputHelper.WriteLine($"Starting ExpertReview workflow via POST request to {startUri}...");
            using HttpResponseMessage startResponse = await s_sharedHttpClient.PostAsync(startUri, content);

            Assert.True(startResponse.IsSuccessStatusCode, $"ExpertReview request failed with status: {startResponse.StatusCode}");
            string startResponseText = await startResponse.Content.ReadAsStringAsync();
            Assert.Contains("ExpertReview", startResponseText);
            this._outputHelper.WriteLine($"ExpertReview response: {startResponseText}");

            // Wait for the ParseQuestion executor to run
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        bool exists = logs.Any(log => log.Message.Contains("[ParseQuestion]"));
                        return Task.FromResult(exists);
                    }
                },
                message: "ParseQuestion executor ran",
                timeout: s_orchestrationTimeout);

            // Wait for the Aggregator to complete (indicates fan-in from parallel agents)
            await this.WaitForConditionAsync(
                condition: () =>
                {
                    lock (logs)
                    {
                        bool exists = logs.Any(log => log.Message.Contains("Aggregation complete"));
                        return Task.FromResult(exists);
                    }
                },
                message: "Aggregator completed with parallel agent responses",
                timeout: s_orchestrationTimeout);

            // Verify the aggregator received responses from both AI agents
            lock (logs)
            {
                Assert.True(
                    logs.Any(log => log.Message.Contains("AI agent responses")),
                    "Aggregator did not log receiving AI agent responses.");
            }
        });
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

            await this.WaitForConditionAsync(this.IsAzuriteRunningAsync, "Azurite is running", TimeSpan.FromSeconds(30));
        }

        // Start DTS emulator if it's not already running
        if (!await this.IsDtsEmulatorRunningAsync())
        {
            await this.StartDockerContainerAsync(
                containerName: "dts-emulator",
                image: "mcr.microsoft.com/dts/dts-emulator:latest",
                ports: ["-p", "8080:8080", "-p", "8082:8082"]);

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
        await this.RunCommandAsync("docker", ["stop", containerName]);
        await this.RunCommandAsync("docker", ["rm", containerName]);

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

    private sealed record OutputLog(DateTime Timestamp, LogLevel Level, string Message);

    private async Task RunSampleTestAsync(string samplePath, bool requiresOpenAI, Func<IReadOnlyList<OutputLog>, Task> testAction)
    {
        // Build the sample project first (it may not have been built as part of the solution)
        await AzureFunctionsTestHelper.BuildSampleAsync(
            samplePath, $"-f {s_dotnetTargetFramework} -c {BuildConfiguration}", this._outputHelper);

        // Start the Azure Functions app
        List<OutputLog> logsContainer = [];
        using Process funcProcess = this.StartFunctionApp(samplePath, logsContainer, requiresOpenAI);
        try
        {
            await AzureFunctionsTestHelper.WaitForFunctionsReadyAsync(
                funcProcess, AzureFunctionsPort, s_sharedHttpClient, this._outputHelper, s_functionsReadyTimeout, samplePath);
            await testAction(logsContainer);
        }
        finally
        {
            await this.StopProcessAsync(funcProcess);
        }
    }

    private Process StartFunctionApp(string samplePath, List<OutputLog> logs, bool requiresOpenAI)
    {
        ProcessStartInfo startInfo = new()
        {
            FileName = "dotnet",
            Arguments = $"run --no-build -f {s_dotnetTargetFramework} -c {BuildConfiguration} --port {AzureFunctionsPort}",
            WorkingDirectory = samplePath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        if (requiresOpenAI)
        {
            string openAiEndpoint = s_configuration["AZURE_OPENAI_ENDPOINT"] ??
                throw new InvalidOperationException("The required AZURE_OPENAI_ENDPOINT env variable is not set.");
            string openAiDeployment = s_configuration["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"] ??
                throw new InvalidOperationException("The required AZURE_OPENAI_CHAT_DEPLOYMENT_NAME env variable is not set.");

            this._outputHelper.WriteLine($"Using Azure OpenAI endpoint: {openAiEndpoint}, deployment: {openAiDeployment}");

            startInfo.EnvironmentVariables["AZURE_OPENAI_ENDPOINT"] = openAiEndpoint;
            startInfo.EnvironmentVariables["AZURE_OPENAI_DEPLOYMENT"] = openAiDeployment;
        }

        startInfo.EnvironmentVariables["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"] =
            $"Endpoint=http://localhost:{DtsPort};TaskHub=default;Authentication=None";
        startInfo.EnvironmentVariables["AzureWebJobsStorage"] = "UseDevelopmentStorage=true";

        Process process = new() { StartInfo = startInfo };

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

    private async Task RunCommandAsync(string command, string[] args)
    {
        ProcessStartInfo startInfo = new()
        {
            FileName = command,
            Arguments = string.Join(" ", args),
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
        string filePath = new Uri(typeof(WorkflowSamplesValidation).Assembly.Location).LocalPath;
        string directory = Path.GetDirectoryName(filePath)!;
        string tfm = Path.GetFileName(directory);
        if (tfm.StartsWith("net", StringComparison.OrdinalIgnoreCase))
        {
            return tfm;
        }

        throw new InvalidOperationException($"Unable to find target framework in path: {filePath}");
    }
}
