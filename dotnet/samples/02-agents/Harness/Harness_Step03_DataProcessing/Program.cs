// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a HarnessAgent with the FileAccessProvider
// to give an agent access to a folder of CSV data files. The agent can read, analyze,
// and extract information from the data, then write results back as new files.
//
// The sample includes a pre-populated `data/` folder with sales transaction data.
// Ask the agent to analyze the data, produce summaries, or create new output files.
//
// Special commands:
//   exit — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.Identity;
using Harness.Shared.Console;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;

// Point the file store at the data/ folder that ships with the sample.
var dataFolder = Path.Combine(AppContext.BaseDirectory, "data");
var fileStore = new FileSystemAgentFileStore(dataFolder);

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

// Create the chat client from the OpenAI provider.
AIAgent agent =
    new OpenAIClient(
        new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions()
        {
            Endpoint = new Uri(endpoint),
            RetryPolicy = new ClientRetryPolicy(3)
        })
    .GetResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "DataAnalyst",
        Description = "A data analyst assistant that reads, analyzes, and processes data files.",
        AIContextProviders =
        [
            new FileAccessProvider(fileStore),
        ],
        ChatOptions = new ChatOptions
        {
            Instructions = instructions,
            MaxOutputTokens = MaxOutputTokens,
        },
    });

// Run the interactive console session.
await HarnessConsole.RunAgentAsync(
    agent,
    title: "Data Processing Assistant",
    userPrompt: "Ask me to analyze the data files, produce summaries, or create output files.");
