// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.IntegrationTests;

/// <summary>
/// Shared test helpers for Azure Functions integration tests.
/// </summary>
internal static class AzureFunctionsTestHelper
{
    private static readonly TimeSpan s_buildTimeout = TimeSpan.FromMinutes(5);

    /// <summary>
    /// Builds the sample project, failing fast if the build fails or times out.
    /// </summary>
    internal static async Task BuildSampleAsync(
        string samplePath,
        string buildArgs,
        ITestOutputHelper outputHelper)
    {
        outputHelper.WriteLine($"Building sample at {samplePath}...");

        ProcessStartInfo buildInfo = new()
        {
            FileName = "dotnet",
            Arguments = $"build {buildArgs}",
            WorkingDirectory = samplePath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        using Process buildProcess = new() { StartInfo = buildInfo };
        buildProcess.Start();

        // Read both streams asynchronously to avoid deadlocks from filled pipe buffers
        Task<string> stdoutTask = buildProcess.StandardOutput.ReadToEndAsync();
        Task<string> stderrTask = buildProcess.StandardError.ReadToEndAsync();

        using CancellationTokenSource buildCts = new(s_buildTimeout);
        try
        {
            await buildProcess.WaitForExitAsync(buildCts.Token);
        }
        catch (OperationCanceledException)
        {
            buildProcess.Kill(entireProcessTree: true);
            throw new TimeoutException($"Build timed out after {s_buildTimeout.TotalMinutes} minutes for sample at {samplePath}.");
        }

        await Task.WhenAll(stdoutTask, stderrTask);

        string stdout = stdoutTask.Result;
        string stderr = stderrTask.Result;
        if (buildProcess.ExitCode != 0)
        {
            throw new InvalidOperationException($"Failed to build sample at {samplePath}:\n{stdout}\n{stderr}");
        }

        outputHelper.WriteLine($"Build completed for {samplePath}.");
    }

    /// <summary>
    /// Polls the Azure Functions host until it responds to an HTTP HEAD request,
    /// failing fast if the host process exits unexpectedly.
    /// </summary>
    internal static async Task WaitForFunctionsReadyAsync(
        Process funcProcess,
        string port,
        HttpClient httpClient,
        ITestOutputHelper outputHelper,
        TimeSpan timeout,
        string? samplePath = null)
    {
        outputHelper.WriteLine(
            $"Waiting for Azure Functions Core Tools to be ready at http://localhost:{port}/...");

        using CancellationTokenSource cts = new(timeout);
        while (true)
        {
            // Fail fast if the host process has exited (e.g. build or startup failure)
            if (funcProcess.HasExited)
            {
                string context = samplePath != null ? $" for sample '{samplePath}'" : string.Empty;
                throw new InvalidOperationException(
                    $"The Azure Functions host process exited unexpectedly with code {funcProcess.ExitCode}{context}.");
            }

            try
            {
                using HttpRequestMessage request = new(HttpMethod.Head, $"http://localhost:{port}/");
                using HttpResponseMessage response = await httpClient.SendAsync(request);
                outputHelper.WriteLine($"Azure Functions Core Tools response: {response.StatusCode}");
                if (response.IsSuccessStatusCode)
                {
                    return;
                }
            }
            catch (HttpRequestException)
            {
                // Expected when the app isn't yet ready
            }

            try
            {
                await Task.Delay(TimeSpan.FromSeconds(1), cts.Token);
            }
            catch (OperationCanceledException) when (cts.IsCancellationRequested)
            {
                string context = samplePath != null ? $" for sample '{samplePath}'" : string.Empty;
                throw new TimeoutException(
                    $"Timeout waiting for 'Azure Functions Core Tools is ready'{context}");
            }
        }
    }
}
