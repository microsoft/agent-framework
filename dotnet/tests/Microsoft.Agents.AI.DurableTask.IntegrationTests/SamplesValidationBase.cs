// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics;
using System.Reflection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

/// <summary>
/// Base class for sample validation integration tests providing shared infrastructure
/// setup and utility methods for running console app samples.
/// </summary>
public abstract class SamplesValidationBase : IAsyncLifetime
{
    protected const string DtsPort = "8080";
    protected const string RedisPort = "6379";

    protected static readonly string DotnetTargetFramework = GetTargetFramework();
    protected static readonly IConfiguration Configuration =
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private static bool s_dtsInfrastructureStarted;
    private static bool s_redisInfrastructureStarted;

    private readonly ITestOutputHelper _outputHelper;

    protected SamplesValidationBase(ITestOutputHelper outputHelper)
    {
        this._outputHelper = outputHelper;
    }

    /// <summary>
    /// Gets the test output helper for logging.
    /// </summary>
    protected ITestOutputHelper OutputHelper => this._outputHelper;

    /// <summary>
    /// Gets the base path to the samples directory for this test class.
    /// </summary>
    protected abstract string SamplesPath { get; }

    /// <summary>
    /// Gets whether this test class requires Redis infrastructure.
    /// </summary>
    protected virtual bool RequiresRedis => false;

    /// <summary>
    /// Gets the task hub name prefix for this test class.
    /// </summary>
    protected virtual string TaskHubPrefix => "sample";

    /// <inheritdoc />
    public async Task InitializeAsync()
    {
        if (!s_dtsInfrastructureStarted)
        {
            this._outputHelper.WriteLine("Starting shared DTS infrastructure...");
            await this.StartDtsEmulatorAsync();
            s_dtsInfrastructureStarted = true;
        }

        if (this.RequiresRedis && !s_redisInfrastructureStarted)
        {
            this._outputHelper.WriteLine("Starting shared Redis infrastructure...");
            await this.StartRedisAsync();
            s_redisInfrastructureStarted = true;
        }

        await Task.Delay(TimeSpan.FromSeconds(5));
    }

    /// <inheritdoc />
    public Task DisposeAsync() => Task.CompletedTask;

    protected sealed record OutputLog(DateTime Timestamp, LogLevel Level, string Message);

    /// <summary>
    /// Runs a sample test by starting the console app and executing the provided test action.
    /// </summary>
    protected async Task RunSampleTestAsync(string samplePath, Func<Process, BlockingCollection<OutputLog>, Task> testAction)
    {
        string uniqueTaskHubName = $"{this.TaskHubPrefix}-{Guid.NewGuid():N}"[..^26];

        using BlockingCollection<OutputLog> logsContainer = [];
        using Process appProcess = this.StartConsoleApp(samplePath, logsContainer, uniqueTaskHubName);

        try
        {
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

    /// <summary>
    /// Writes a line to the process's stdin and flushes it.
    /// </summary>
    protected async Task WriteInputAsync(Process process, string input, CancellationToken cancellationToken)
    {
        this._outputHelper.WriteLine($"{DateTime.Now:HH:mm:ss.fff} [{process.ProcessName}(in)]: {input}");
        await process.StandardInput.WriteLineAsync(input);
        await process.StandardInput.FlushAsync(cancellationToken);
    }

    /// <summary>
    /// Reads the next Information-level log line from the queue.
    /// Returns null if cancelled or collection is completed.
    /// </summary>
    protected string? ReadLogLine(BlockingCollection<OutputLog> logs, CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                OutputLog log = logs.Take(cancellationToken);

                if (log.Message.Contains("Unhandled exception"))
                {
                    Assert.Fail("Console app encountered an unhandled exception.");
                }

                if (log.Level == LogLevel.Information)
                {
                    return log.Message;
                }
            }
        }
        catch (OperationCanceledException)
        {
            return null;
        }
        catch (InvalidOperationException)
        {
            return null;
        }

        return null;
    }

    /// <summary>
    /// Creates a cancellation token source with the specified timeout for test operations.
    /// </summary>
    protected CancellationTokenSource CreateTestTimeoutCts(TimeSpan? timeout = null)
    {
        TimeSpan testTimeout = Debugger.IsAttached ? TimeSpan.FromMinutes(5) : timeout ?? TimeSpan.FromSeconds(60);
        return new CancellationTokenSource(testTimeout);
    }

    /// <summary>
    /// Allows derived classes to set additional environment variables for the console app process.
    /// </summary>
    protected virtual void ConfigureAdditionalEnvironmentVariables(ProcessStartInfo startInfo, Action<string, string> setEnvVar)
    {
    }

    private static string GetTargetFramework()
    {
        string filePath = new Uri(typeof(SamplesValidationBase).Assembly.Location).LocalPath;
        string directory = Path.GetDirectoryName(filePath)!;
        string tfm = Path.GetFileName(directory);
        if (tfm.StartsWith("net", StringComparison.OrdinalIgnoreCase))
        {
            return tfm;
        }

        throw new InvalidOperationException($"Unable to find target framework in path: {filePath}");
    }

    private async Task StartDtsEmulatorAsync()
    {
        if (!await this.IsDtsEmulatorRunningAsync())
        {
            this._outputHelper.WriteLine("Starting DTS emulator...");
            await this.RunCommandAsync("docker", "run", "-d",
                "--name", "dts-emulator",
                "-p", $"{DtsPort}:8080",
                "-e", "DTS_USE_DYNAMIC_TASK_HUBS=true",
                "mcr.microsoft.com/dts/dts-emulator:latest");
        }
    }

    private async Task StartRedisAsync()
    {
        if (!await this.IsRedisRunningAsync())
        {
            this._outputHelper.WriteLine("Starting Redis...");
            await this.RunCommandAsync("docker", "run", "-d",
                "--name", "redis",
                "-p", $"{RedisPort}:6379",
                "redis:latest");
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
            using HttpResponseMessage response = await http2Client.GetAsync(
                new Uri($"http://localhost:{DtsPort}/healthz"), timeoutCts.Token);

            if (response.Content.Headers.ContentLength > 0)
            {
                string content = await response.Content.ReadAsStringAsync(timeoutCts.Token);
                this._outputHelper.WriteLine($"DTS emulator health check response: {content}");
            }

            bool isRunning = response.IsSuccessStatusCode;
            this._outputHelper.WriteLine(isRunning ? "DTS emulator is running" : $"DTS emulator not running. Status: {response.StatusCode}");
            return isRunning;
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

            bool isRunning = process.ExitCode == 0 && output.Contains("PONG", StringComparison.OrdinalIgnoreCase);
            this._outputHelper.WriteLine(isRunning ? "Redis is running" : $"Redis not running. Exit: {process.ExitCode}, Output: {output}");
            return isRunning;
        }
        catch (Exception ex)
        {
            this._outputHelper.WriteLine($"Redis is not running: {ex.Message}");
            return false;
        }
    }

    private Process StartConsoleApp(string samplePath, BlockingCollection<OutputLog> logs, string taskHubName)
    {
        ProcessStartInfo startInfo = new()
        {
            FileName = "dotnet",
            Arguments = $"run --framework {DotnetTargetFramework}",
            WorkingDirectory = samplePath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
        };

        string openAiEndpoint = Configuration["AZURE_OPENAI_ENDPOINT"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_ENDPOINT env variable is not set.");
        string openAiDeployment = Configuration["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_CHAT_DEPLOYMENT_NAME env variable is not set.");

        void SetAndLogEnvironmentVariable(string key, string value)
        {
            this._outputHelper.WriteLine($"Setting environment variable for {startInfo.FileName} sub-process: {key}={value}");
            startInfo.EnvironmentVariables[key] = value;
        }

        SetAndLogEnvironmentVariable("AZURE_OPENAI_ENDPOINT", openAiEndpoint);
        SetAndLogEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT", openAiDeployment);
        SetAndLogEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING",
            $"Endpoint=http://localhost:{DtsPort};TaskHub={taskHubName};Authentication=None");

        this.ConfigureAdditionalEnvironmentVariables(startInfo, SetAndLogEnvironmentVariable);

        Process process = new() { StartInfo = startInfo };

        process.ErrorDataReceived += (sender, e) => this.HandleProcessOutput(e.Data, startInfo.FileName, "err", LogLevel.Error, logs);
        process.OutputDataReceived += (sender, e) => this.HandleProcessOutput(e.Data, startInfo.FileName, "out", LogLevel.Information, logs);

        if (!process.Start())
        {
            throw new InvalidOperationException("Failed to start the console app");
        }

        process.BeginErrorReadLine();
        process.BeginOutputReadLine();

        return process;
    }

    private void HandleProcessOutput(string? data, string processName, string stream, LogLevel level, BlockingCollection<OutputLog> logs)
    {
        if (data is null)
        {
            return;
        }

        string logMessage = $"{DateTime.Now:HH:mm:ss.fff} [{processName}({stream})]: {data}";
        this._outputHelper.WriteLine(logMessage);
        Debug.WriteLine(logMessage);

        try
        {
            logs.Add(new OutputLog(DateTime.Now, level, data));
        }
        catch (InvalidOperationException)
        {
            // Collection completed
        }
    }

    private async Task RunCommandAsync(string command, params string[] args)
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

        using CancellationTokenSource cts = new(TimeSpan.FromMinutes(1));
        await process.WaitForExitAsync(cts.Token);

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

                using CancellationTokenSource cts = new(TimeSpan.FromSeconds(10));
                await process.WaitForExitAsync(cts.Token);
                this._outputHelper.WriteLine($"{DateTime.Now:HH:mm:ss.fff} Process exited: {process.Id}");
            }
        }
        catch (Exception ex)
        {
            this._outputHelper.WriteLine($"{DateTime.Now:HH:mm:ss.fff} Failed to stop process: {ex.Message}");
        }
    }
}
