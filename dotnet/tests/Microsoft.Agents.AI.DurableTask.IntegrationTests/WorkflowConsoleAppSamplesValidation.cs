// Copyright (c) Microsoft. All rights reserved.

using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

/// <summary>
/// Integration tests for validating the durable workflow console app samples
/// located in samples/Durable/Workflow/ConsoleApps.
/// </summary>
[Collection("Samples")]
[Trait("Category", "SampleValidation")]
public sealed class WorkflowConsoleAppSamplesValidation(ITestOutputHelper outputHelper) : SamplesValidationBase(outputHelper)
{
    private static readonly string s_samplesPath = Path.GetFullPath(
        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", "..", "..", "samples", "Durable", "Workflow", "ConsoleApps"));

    /// <inheritdoc />
    protected override string SamplesPath => s_samplesPath;

    /// <inheritdoc />
    protected override string TaskHubPrefix => "workflow";

    [Fact]
    public async Task SequentialWorkflowSampleValidationAsync()
    {
        using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();
        string samplePath = Path.Combine(s_samplesPath, "01_SequentialWorkflow");

        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            bool inputSent = false;
            bool workflowCompleted = false;
            bool foundOrderLookup = false;
            bool foundOrderCancel = false;
            bool foundSendEmail = false;

            string? line;
            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                if (!inputSent && line.Contains("Enter an order ID", StringComparison.OrdinalIgnoreCase))
                {
                    await this.WriteInputAsync(process, "12345", testTimeoutCts.Token);
                    inputSent = true;
                }

                if (inputSent)
                {
                    foundOrderLookup |= line.Contains("[Activity] OrderLookup:", StringComparison.Ordinal);
                    foundOrderCancel |= line.Contains("[Activity] OrderCancel:", StringComparison.Ordinal);
                    foundSendEmail |= line.Contains("[Activity] SendEmail:", StringComparison.Ordinal);

                    if (line.Contains("Workflow completed. Cancellation email sent for order 12345", StringComparison.OrdinalIgnoreCase))
                    {
                        workflowCompleted = true;
                        break;
                    }
                }

                this.AssertNoError(line);
            }

            Assert.True(inputSent, "Input was not sent to the workflow.");
            Assert.True(foundOrderLookup, "OrderLookup executor log entry not found.");
            Assert.True(foundOrderCancel, "OrderCancel executor log entry not found.");
            Assert.True(foundSendEmail, "SendEmail executor log entry not found.");
            Assert.True(workflowCompleted, "Workflow did not complete successfully.");

            await this.WriteInputAsync(process, "exit", testTimeoutCts.Token);
        });
    }

    [Fact]
    public async Task ConcurrentWorkflowSampleValidationAsync()
    {
        using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();
        string samplePath = Path.Combine(s_samplesPath, "02_ConcurrentWorkflow");

        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            bool inputSent = false;
            bool workflowCompleted = false;
            bool foundParseQuestion = false;
            bool foundAggregator = false;
            bool foundAggregatorReceived2Responses = false;

            string? line;
            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                if (!inputSent && line.Contains("Enter a science question", StringComparison.OrdinalIgnoreCase))
                {
                    await this.WriteInputAsync(process, "What is gravity?", testTimeoutCts.Token);
                    inputSent = true;
                }

                if (inputSent)
                {
                    foundParseQuestion |= line.Contains("[ParseQuestion]", StringComparison.Ordinal);
                    foundAggregator |= line.Contains("[Aggregator]", StringComparison.Ordinal);
                    foundAggregatorReceived2Responses |= line.Contains("Received 2 AI agent responses", StringComparison.Ordinal);

                    if (line.Contains("Aggregation complete", StringComparison.OrdinalIgnoreCase))
                    {
                        workflowCompleted = true;
                        break;
                    }
                }

                this.AssertNoError(line);
            }

            Assert.True(inputSent, "Input was not sent to the workflow.");
            Assert.True(foundParseQuestion, "ParseQuestion executor log entry not found.");
            Assert.True(foundAggregator, "Aggregator executor log entry not found.");
            Assert.True(foundAggregatorReceived2Responses, "Aggregator did not receive 2 AI agent responses.");
            Assert.True(workflowCompleted, "Workflow did not complete successfully.");

            await this.WriteInputAsync(process, "exit", testTimeoutCts.Token);
        });
    }

    private void AssertNoError(string line)
    {
        if (line.Contains("Failed:", StringComparison.OrdinalIgnoreCase) ||
            line.Contains("Error:", StringComparison.OrdinalIgnoreCase))
        {
            Assert.Fail($"Workflow failed: {line}");
        }
    }
}
