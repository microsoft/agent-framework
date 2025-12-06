// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.AspNetCore.HttpLogging;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Options;
using OpenAI.Chat;
using ServerFunctionApproval;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

builder.Services.AddHttpLogging(logging =>
{
    logging.LoggingFields = HttpLoggingFields.RequestPropertiesAndHeaders | HttpLoggingFields.RequestBody
        | HttpLoggingFields.ResponsePropertiesAndHeaders | HttpLoggingFields.ResponseBody;
    logging.RequestBodyLogLimit = int.MaxValue;
    logging.ResponseBodyLogLimit = int.MaxValue;
});

builder.Services.AddHttpClient().AddLogging();
builder.Services.ConfigureHttpJsonOptions(options =>
    options.SerializerOptions.TypeInfoResolverChain.Add(ApprovalJsonContext.Default));
builder.Services.AddAGUI();

WebApplication app = builder.Build();

app.UseHttpLogging();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Define approval-required tool
[Description("Approve the expense report.")]
static string ApproveExpenseReport(string expenseReportId)
{
    return $"Expense report {expenseReportId} approved";
}

// Get JsonSerializerOptions
var jsonOptions = app.Services.GetRequiredService<IOptions<JsonOptions>>().Value;

// Create approval-required tool
#pragma warning disable MEAI001 // Type is for evaluation purposes only
AITool[] tools = [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(ApproveExpenseReport))];
#pragma warning restore MEAI001

// Create base agent
ChatClient openAIChatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName);

ChatClientAgent baseAgent = openAIChatClient.AsIChatClient().CreateAIAgent(
    name: "AGUIAssistant",
    instructions: "You are a helpful assistant in charge of approving expenses",
    tools: tools);

// Wrap with ServerFunctionApprovalAgent
var agent = new ServerFunctionApprovalAgent(baseAgent, jsonOptions.SerializerOptions);

app.MapAGUI("/", agent);
await app.RunAsync();
