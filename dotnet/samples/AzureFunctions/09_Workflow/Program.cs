// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI.Chat;
using SingleAgent;

// Get the Azure OpenAI endpoint and deployment name from environment variables.
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT is not set.");

// Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
string? azureOpenAiKey = System.Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");
AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());

// Set up an AI agent following the standard Microsoft Agent Framework pattern.
const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";
const string AnalysisInstructions = @"You are a Customer Feedback Analyzer. Your task is to analyze customer survey responses and categorize them accurately.

INPUT: You will receive customer feedback text that may include a rating and comments.

OUTPUT: Return ONLY ONE category from this list:
- Bug Report
- General Feedback
- Billing Question
- Support Incident Status

CATEGORIZATION RULES:
- ""Bug Report"": Technical issues, errors, crashes, features not working as expected
- ""General Feedback"": Suggestions, compliments, general comments about the product or service
- ""Billing Question"": Payment issues, subscription inquiries, pricing questions, refund requests
- ""Support Incident Status"": Follow-ups on existing tickets, status inquiries about previous issues

RESPONSE FORMAT: Return only the category name exactly as shown above, with no additional text or explanation.

Examples:
- ""The app crashes when I try to export"" → Bug Report
- ""Love the new design! Great work"" → General Feedback
- ""Why was I charged twice this month?"" → Billing Question
- ""What's the status of ticket #12345?"" → Support Incident Status";
AIAgent agent = client.GetChatClient(deploymentName).CreateAIAgent(JokerInstructions, JokerName);
AIAgent agent2 = client.GetChatClient(deploymentName).CreateAIAgent(AnalysisInstructions, "FeedbackAnalysisBot");

SurveyResponseParserExecutor surveyResponseParserExecutor = new();
ResponseRouterExecutor responseRouterExecutor = new();

WorkflowBuilder builder = new(surveyResponseParserExecutor);
builder.AddEdge(surveyResponseParserExecutor, agent2);
builder.AddEdge(agent2, responseRouterExecutor).WithOutputFrom(responseRouterExecutor);

var workflow = builder.WithName("HandleSurveyResponse").Build();

// Configure the function app to host AI agents and workflows in a unified way.
// This will automatically generate HTTP API endpoints for agents and workflows.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    //.ConfigureDurableAgents(op => op.AddAIAgent(agent, timeToLive: TimeSpan.FromHours(1)))
    .ConfigureDurableOptions(options =>
    {
        // Configure workflows
        options.Workflows.AddWorkflow(workflow);
    })
    .Build();
app.Run();
