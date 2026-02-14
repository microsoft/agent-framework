// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Reflection;
using System.Text;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.IntegrationTests;

/// <summary>
/// Integration tests for validating the durable workflow Azure Functions samples
/// located in samples/Durable/Workflow/AzureFunctions.
/// </summary>
[Collection("Samples")]
[Trait("Category", "SampleValidation")]
public sealed class WorkflowSamplesValidation(ITestOutputHelper outputHelper) : IAsyncLifetime
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
        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", "..", "..", "samples", "Durable", "Workflow", "AzureFunctions"));

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
        await Task.CompletedTask;
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
        List<OutputLog> logsContainer = [];
        using Process funcProcess = this.StartFunctionApp(samplePath, logsContainer, requiresOpenAI);
        try
        {
            await this.WaitForAzureFunctionsAsync();
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
            Arguments = $"run -f {s_dotnetTargetFramework} --port {AzureFunctionsPort}",
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
                    return false;
                }
            },
            message: "Azure Functions Core Tools is ready",
            timeout: TimeSpan.FromSeconds(60));
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
