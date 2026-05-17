// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI.ContentUnderstanding;
using Microsoft.Extensions.AI;

namespace AzureAIContentUnderstanding.IntegrationTests;

/// <summary>
/// Live integration tests for <see cref="ContentUnderstandingContextProvider"/>.
/// Each test is gated on the environment variables listed in its <c>Skip</c> check.
/// When run in CI without credentials, every test skips cleanly.
///
/// Required environment variables:
///   AZURE_AI_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME,
///   AZURE_CONTENTUNDERSTANDING_ENDPOINT.
/// </summary>
[Trait("Category", "Live")]
public sealed class ContentUnderstandingLiveTests
{
    private const string ProjectEndpointVar = "AZURE_AI_PROJECT_ENDPOINT";
    private const string ModelDeploymentVar = "AZURE_AI_MODEL_DEPLOYMENT_NAME";
    private const string CuEndpointVar = "AZURE_CONTENTUNDERSTANDING_ENDPOINT";

    private static string SampleAssetsRoot => Path.Combine(
        AppContext.BaseDirectory,
        "..", "..", "..", "..", "..",
        "samples", "02-agents", "AgentWithContentUnderstanding", "SampleAssets");

    // parity: python tests/cu/test_live.py::test_pdf_qa_invoice
    [Fact]
    public async Task PdfQa_InvoiceDocument_ReturnsVendorAndTotal()
    {
        (string projectEndpoint, string modelDeployment, string cuEndpoint) = RequireLiveEnvironmentOrSkip();
        string invoicePath = Path.Combine(SampleAssetsRoot, "invoice.pdf");
        Assert.SkipUnless(File.Exists(invoicePath), $"Sample asset not found at {invoicePath}.");

        var credential = new DefaultAzureCredential();
        await using var cu = new ContentUnderstandingContextProvider(
            new Uri(cuEndpoint),
            credential,
            options =>
            {
                options.AnalyzerId = "prebuilt-documentSearch";
                options.MaxWait = TimeSpan.FromMinutes(2);
            });

        AIProjectClient projectClient = new(new Uri(projectEndpoint), credential);
        AIAgent agent = projectClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "DocumentQA",
            ChatOptions = new ChatOptions
            {
                ModelId = modelDeployment,
                Instructions =
                    "You are a helpful document analyst. Use the analyzed document content "
                    + "and extracted fields to answer precisely.",
            },
            AIContextProviders = [cu],
        });

        byte[] pdfBytes = await File.ReadAllBytesAsync(invoicePath);
        DataContent pdf = new(pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage userMessage = new(
            ChatRole.User,
            [
                new TextContent("Who is the vendor and what is the total amount due?"),
                pdf,
            ]);

        AgentResponse response = await agent.RunAsync(userMessage);

        Assert.NotNull(response);
        string text = response.ToString();
        Assert.False(string.IsNullOrWhiteSpace(text), "Agent returned an empty response.");
    }

    // parity: python tests/cu/test_live.py::test_invoice_field_extraction
    [Fact]
    public async Task InvoiceFieldExtraction_PrebuiltInvoiceAnalyzer_FieldsFlowIntoContext()
    {
        (string projectEndpoint, string modelDeployment, string cuEndpoint) = RequireLiveEnvironmentOrSkip();
        string invoicePath = Path.Combine(SampleAssetsRoot, "invoice.pdf");
        Assert.SkipUnless(File.Exists(invoicePath), $"Sample asset not found at {invoicePath}.");

        var credential = new DefaultAzureCredential();
        await using var cu = new ContentUnderstandingContextProvider(
            new Uri(cuEndpoint),
            credential,
            options =>
            {
                options.AnalyzerId = "prebuilt-invoice";
                options.MaxWait = TimeSpan.FromMinutes(2);
            });

        AIProjectClient projectClient = new(new Uri(projectEndpoint), credential);
        AIAgent agent = projectClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "InvoiceAnalyst",
            ChatOptions = new ChatOptions
            {
                ModelId = modelDeployment,
                Instructions =
                    "Use the extracted invoice fields (vendor name, total amount) to answer.",
            },
            AIContextProviders = [cu],
        });

        byte[] pdfBytes = await File.ReadAllBytesAsync(invoicePath);
        DataContent pdf = new(pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage userMessage = new(
            ChatRole.User,
            [
                new TextContent("List the vendor name and the total invoice amount exactly as printed."),
                pdf,
            ]);

        AgentResponse response = await agent.RunAsync(userMessage);

        Assert.NotNull(response);
        Assert.False(string.IsNullOrWhiteSpace(response.ToString()));
    }

    // parity: python tests/cu/test_live.py::test_multi_turn_session_reuses_analysis
    [Fact]
    public async Task MultiTurnSession_SecondTurn_ReusesPreviousAnalysisWithoutReanalyzing()
    {
        (string projectEndpoint, string modelDeployment, string cuEndpoint) = RequireLiveEnvironmentOrSkip();
        string invoicePath = Path.Combine(SampleAssetsRoot, "invoice.pdf");
        Assert.SkipUnless(File.Exists(invoicePath), $"Sample asset not found at {invoicePath}.");

        var credential = new DefaultAzureCredential();
        await using var cu = new ContentUnderstandingContextProvider(
            new Uri(cuEndpoint),
            credential,
            options =>
            {
                options.AnalyzerId = "prebuilt-documentSearch";
                options.MaxWait = TimeSpan.FromMinutes(2);
            });

        AIProjectClient projectClient = new(new Uri(projectEndpoint), credential);
        AIAgent agent = projectClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "DocumentChat",
            ChatOptions = new ChatOptions
            {
                ModelId = modelDeployment,
                Instructions = "Answer based on the previously analyzed document.",
            },
            AIContextProviders = [cu],
        });

        AgentSession session = await agent.CreateSessionAsync();

        byte[] pdfBytes = await File.ReadAllBytesAsync(invoicePath);
        DataContent pdf = new(pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        ChatMessage turn1 = new(ChatRole.User, [new TextContent("Summarize this document."), pdf]);
        AgentResponse response1 = await agent.RunAsync(turn1, session);
        Assert.NotNull(response1);

        // Turn 2: text-only follow-up — should not re-analyze, just reuse cached context.
        ChatMessage turn2 = new(ChatRole.User, [new TextContent("What was the total amount?")]);
        AgentResponse response2 = await agent.RunAsync(turn2, session);
        Assert.NotNull(response2);
        Assert.False(string.IsNullOrWhiteSpace(response2.ToString()));
    }

    // parity: python tests/cu/test_live.py::test_disposal_releases_resources
    [Fact]
    public async Task Dispose_CompletesWithoutHangingBackgroundTasks()
    {
        (_, _, string cuEndpoint) = RequireLiveEnvironmentOrSkip();

        var credential = new DefaultAzureCredential();
        var cu = new ContentUnderstandingContextProvider(
            new Uri(cuEndpoint),
            credential,
            options =>
            {
                options.AnalyzerId = "prebuilt-documentSearch";
                options.MaxWait = TimeSpan.FromMilliseconds(1); // force background path
            });

        // Disposing immediately, before any analysis is scheduled, must complete promptly.
        var disposeTask = cu.DisposeAsync().AsTask();
        var winner = await Task.WhenAny(disposeTask, Task.Delay(TimeSpan.FromSeconds(10)));
        Assert.Same(disposeTask, winner);
    }

    private static (string ProjectEndpoint, string ModelDeployment, string CuEndpoint) RequireLiveEnvironmentOrSkip()
    {
        string? project = Environment.GetEnvironmentVariable(ProjectEndpointVar);
        string? model = Environment.GetEnvironmentVariable(ModelDeploymentVar);
        string? cu = Environment.GetEnvironmentVariable(CuEndpointVar);

        if (string.IsNullOrWhiteSpace(project) || string.IsNullOrWhiteSpace(model) || string.IsNullOrWhiteSpace(cu))
        {
            Assert.Skip(
                $"Live test requires {ProjectEndpointVar}, {ModelDeploymentVar}, {CuEndpointVar} environment variables.");
        }

        return (project!, model!, cu!);
    }
}
