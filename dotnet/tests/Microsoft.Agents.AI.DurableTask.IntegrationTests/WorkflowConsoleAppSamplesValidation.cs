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

    [Fact]
    public async Task ConditionalEdgesWorkflowSampleValidationAsync()
    {
        using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();
        string samplePath = Path.Combine(s_samplesPath, "03_ConditionalEdges");

        await this.RunSampleTestAsync(samplePath, async (process, logs) =>
        {
            bool validOrderSent = false;
            bool blockedOrderSent = false;
            bool validOrderCompleted = false;
            bool blockedOrderCompleted = false;

            string? line;
            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                // Send a valid order first (no 'B' in ID)
                if (!validOrderSent && line.Contains("Enter an order ID", StringComparison.OrdinalIgnoreCase))
                {
                    await this.WriteInputAsync(process, "12345", testTimeoutCts.Token);
                    validOrderSent = true;
                }

                // Check valid order completed (routed to PaymentProcessor)
                if (validOrderSent && !validOrderCompleted &&
                    line.Contains("PaymentReferenceNumber", StringComparison.OrdinalIgnoreCase))
                {
                    validOrderCompleted = true;

                    // Send a blocked order (contains 'B')
                    await this.WriteInputAsync(process, "ORDER-B-999", testTimeoutCts.Token);
                    blockedOrderSent = true;
                }

                // Check blocked order completed (routed to NotifyFraud)
                if (blockedOrderSent && line.Contains("flagged as fraudulent", StringComparison.OrdinalIgnoreCase))
                {
                    blockedOrderCompleted = true;
                    break;
                }

                this.AssertNoError(line);
            }

            Assert.True(validOrderSent, "Valid order input was not sent.");
            Assert.True(validOrderCompleted, "Valid order did not complete (PaymentProcessor path).");
            Assert.True(blockedOrderSent, "Blocked order input was not sent.");
            Assert.True(blockedOrderCompleted, "Blocked order did not complete (NotifyFraud path).");

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

    [Fact]
    public async Task WorkflowAndAgentsSampleValidationAsync()
    {
        using CancellationTokenSource testTimeoutCts = this.CreateTestTimeoutCts();
        string samplePath = Path.Combine(s_samplesPath, "04_WorkflowAndAgents");

        await this.RunSampleTestAsync(samplePath, (process, logs) =>
        {
            // Arrange
            bool foundDemo1 = false;
            bool foundBiologistResponse = false;
            bool foundChemistResponse = false;
            bool foundDemo2 = false;
            bool foundPhysicsWorkflow = false;
            bool foundDemo3 = false;
            bool foundExpertTeamWorkflow = false;
            bool foundDemo4 = false;
            bool foundChemistryWorkflow = false;
            bool allDemosCompleted = false;

            // Act
            string? line;
            while ((line = this.ReadLogLine(logs, testTimeoutCts.Token)) != null)
            {
                foundDemo1 |= line.Contains("DEMO 1:", StringComparison.Ordinal);
                foundBiologistResponse |= line.Contains("Biologist:", StringComparison.Ordinal);
                foundChemistResponse |= line.Contains("Chemist:", StringComparison.Ordinal);
                foundDemo2 |= line.Contains("DEMO 2:", StringComparison.Ordinal);
                foundPhysicsWorkflow |= line.Contains("PhysicsExpertReview", StringComparison.Ordinal);
                foundDemo3 |= line.Contains("DEMO 3:", StringComparison.Ordinal);
                foundExpertTeamWorkflow |= line.Contains("ExpertTeamReview", StringComparison.Ordinal);
                foundDemo4 |= line.Contains("DEMO 4:", StringComparison.Ordinal);
                foundChemistryWorkflow |= line.Contains("ChemistryExpertReview", StringComparison.Ordinal);

                if (line.Contains("All demos completed", StringComparison.OrdinalIgnoreCase))
                {
                    allDemosCompleted = true;
                    break;
                }

                this.AssertNoError(line);
            }

            // Assert
            Assert.True(foundDemo1, "DEMO 1 (Direct Agent Conversation) not found.");
            Assert.True(foundBiologistResponse, "Biologist agent response not found.");
            Assert.True(foundChemistResponse, "Chemist agent response not found.");
            Assert.True(foundDemo2, "DEMO 2 (Single-Agent Workflow) not found.");
            Assert.True(foundPhysicsWorkflow, "PhysicsExpertReview workflow not found.");
            Assert.True(foundDemo3, "DEMO 3 (Multi-Agent Workflow) not found.");
            Assert.True(foundExpertTeamWorkflow, "ExpertTeamReview workflow not found.");
            Assert.True(foundDemo4, "DEMO 4 (Chemistry Workflow) not found.");
            Assert.True(foundChemistryWorkflow, "ChemistryExpertReview workflow not found.");
            Assert.True(allDemosCompleted, "Sample did not complete all demos successfully.");

            return Task.CompletedTask;
        });
    }
}
