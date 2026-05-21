// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a HarnessAgent with the default FileAccessProvider
// to give an agent access to a folder of CSV data files. The agent can read, analyze,
// and extract information from the data, then write results back as new files.
//
// The sample includes a pre-populated `working/` folder with sales transaction data.
// The HarnessAgent's default FileAccessProvider uses `{cwd}/working` as its working directory,
// which matches this sample's folder layout.
// Ask the agent to analyze the data, produce summaries, or create new output files.
//
// Special commands:
//   /exit — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using Harness.Shared.Console;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;
const string TracingSourceName = "Harness.DataProcessing";

// Set up OpenTelemetry tracing that writes spans to a text file.
using var tracerProvider = HarnessTracing.CreateFileTracerProvider(TracingSourceName);

var instructions =
    """
    You are a data analyst assistant. You have access to a folder of data files via the FileAccess_* tools.

    ## Getting started
    - Start by listing available files with FileAccess_ListFiles to see what data is available.
    - Read the files to understand their structure and contents.

    ## Working with data
    - When asked to analyze data, read the relevant files first, then perform the analysis.
    - Show your analysis clearly with tables, summaries, and key insights.
    - When calculations are needed, work through them step by step and show your reasoning.

    ## Writing output
    - When asked to produce output files (e.g., reports, summaries, filtered data), use FileAccess_SaveFile to write them.
    - Use appropriate file formats: CSV for tabular data, Markdown for reports.
    - Confirm what you wrote and where.

    ## Important
    - Never modify or delete the original input data files unless explicitly asked to do so.
    - If asked about data you haven't read yet, read it first before answering.
    - Always explain your reasoning and thought process as you work through tasks.
    - Always explain what you learned and what you are going to do next between tool calls, so the user can follow along with your thought process.
    """;

// Create the agent using AsHarnessAgent. The FileAccessStore is explicitly set to the
// sample's working/ folder (copied to the output directory) so it works regardless of cwd.
// Unused features are disabled.
AIAgent agent =
    new AIProjectClient(
        new Uri(endpoint),
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "DataAnalyst",
        Description = "A data analyst assistant that reads, analyzes, and processes data files.",
        OpenTelemetrySourceName = TracingSourceName,
        FileAccessStore = new FileSystemAgentFileStore(Path.Combine(AppContext.BaseDirectory, "working")),
        DisableTodoProvider = true,
        DisableAgentModeProvider = true,
        DisableFileMemory = true,   // If enabled, this would allow the agent to store memories as files in a directory associated with the current session
        DisableWebSearch = true,
        ChatOptions = new ChatOptions
        {
            Instructions = instructions,
            MaxOutputTokens = MaxOutputTokens,
        },
    });

// Run the interactive console session.
await HarnessConsole.RunAgentAsync(
    agent,
    userPrompt: "Ask me to analyze the data files, produce summaries, or create output files.");
