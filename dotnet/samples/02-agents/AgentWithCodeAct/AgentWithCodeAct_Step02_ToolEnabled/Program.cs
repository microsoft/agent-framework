// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use HyperlightCodeActProvider with provider-owned
// tools (exposed inside the sandbox via `call_tool(...)`). The model can
// orchestrate those tools in a single Python block, reducing round-trips. A
// sensitive tool (`send_email`) is additionally wrapped in
// ApprovalRequiredAIFunction so any code that reaches it requires user approval
// for the entire execute_code invocation.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hyperlight;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
var guestPath = Environment.GetEnvironmentVariable("HYPERLIGHT_PYTHON_GUEST_PATH") ?? throw new InvalidOperationException("HYPERLIGHT_PYTHON_GUEST_PATH is not set.");

AIFunction fetchDocs = AIFunctionFactory.Create(
    (string topic) => $"Docs for {topic}: (...)",
    name: "fetch_docs",
    description: "Fetch documentation for a given topic.");

AIFunction queryData = AIFunctionFactory.Create(
    (string query) => $"Rows for `{query}`: []",
    name: "query_data",
    description: "Run a read-only SQL-like query against the sample store.");

AIFunction sendEmail = new ApprovalRequiredAIFunction(
    AIFunctionFactory.Create(
        (string to, string subject) => $"Sent '{subject}' to {to}.",
        name: "send_email",
        description: "Send an email on behalf of the user."));

var options = HyperlightCodeActProviderOptions.CreateForWasm(guestPath);
options.Tools = [fetchDocs, queryData, sendEmail];

using var codeAct = new HyperlightCodeActProvider(options);

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions()
    {
        ChatOptions = new() { Instructions = "You are a helpful assistant. Prefer orchestrating your work in a single `execute_code` block using `call_tool(...)` over issuing many direct tool calls." },
        AIContextProviders = [codeAct],
    });

Console.WriteLine(await agent.RunAsync("Look up docs on 'retries' and query the 'orders' table, then summarize."));
