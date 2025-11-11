// Copyright (c) Microsoft. All rights reserved.

using A2A.AspNetCore;
using AgentWebChat.AgentHost;
using AgentWebChat.AgentHost.Custom;
using AgentWebChat.AgentHost.Utilities;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

var builder = WebApplication.CreateBuilder(args);

// Add service defaults & Aspire client integrations.
builder.AddServiceDefaults();
builder.Services.AddOpenApi();

// Add services to the container.
builder.Services.AddProblemDetails();

// Configure the chat model and our agent.
builder.AddKeyedChatClient("chat-model");

var pirateAgentBuilder = builder.AddAIAgent(
    "pirate",
    instructions: "You are a pirate. Speak like a pirate",
    description: "An agent that speaks like a pirate.",
    chatClientServiceKey: "chat-model")
    .WithAITool(new CustomAITool())
    .WithAITool(new CustomFunctionTool())
    .WithInMemoryThreadStore();

var knightsKnavesAgentBuilder = builder.AddAIAgent("knights-and-knaves", (sp, key) =>
{
    var chatClient = sp.GetRequiredKeyedService<IChatClient>("chat-model");

    ChatClientAgent knight = new(
        chatClient,
        """
        You are a knight. This means that you must always tell the truth. Your name is Alice.
        Bob is standing next to you. Bob is a knave, which means he always lies.
        When replying, always start with your name (Alice). Eg, "Alice: I am a knight."
        """, "Alice");

    ChatClientAgent knave = new(
        chatClient,
        """
        You are a knave. This means that you must always lie. Your name is Bob.
        Alice is standing next to you. Alice is a knight, which means she always tells the truth.
        When replying, always include your name (Bob). Eg, "Bob: I am a knight."
        """, "Bob");

    ChatClientAgent narrator = new(
        chatClient,
        """
        You are are the narrator of a puzzle involving knights (who always tell the truth) and knaves (who always lie).
        The user is going to ask questions and guess whether Alice or Bob is the knight or knave.
        Alice is standing to one side of you. Alice is a knight, which means she always tells the truth.
        Bob is standing to the other side of you. Bob is a knave, which means he always lies.
        When replying, always include your name (Narrator).
        Once the user has deduced what type (knight or knave) both Alice and Bob are, tell them whether they are right or wrong.
        If the user asks a general question about their surrounding, make something up which is consistent with the scenario.
        """, "Narrator");

    return AgentWorkflowBuilder.BuildConcurrent([knight, knave, narrator]).AsAgent(name: key);
});

// Workflow consisting of multiple specialized agents
var chemistryAgent = builder.AddAIAgent("chemist",
    instructions: "You are a chemistry expert. Answer thinking from the chemistry perspective",
    description: "An agent that helps with chemistry.",
    chatClientServiceKey: "chat-model");

var mathsAgent = builder.AddAIAgent("mathematician",
    instructions: "You are a mathematics expert. Answer thinking from the maths perspective",
    description: "An agent that helps with mathematics.",
    chatClientServiceKey: "chat-model");

var literatureAgent = builder.AddAIAgent("literator",
    instructions: "You are a literature expert. Answer thinking from the literature perspective",
    description: "An agent that helps with literature.",
    chatClientServiceKey: "chat-model");

var scienceSequentialWorkflow = builder.AddWorkflow("science-sequential-workflow", (sp, key) =>
{
    List<IHostedAgentBuilder> usedAgents = [chemistryAgent, mathsAgent, literatureAgent];
    var agents = usedAgents.Select(ab => sp.GetRequiredKeyedService<AIAgent>(ab.Name));
    return AgentWorkflowBuilder.BuildSequential(workflowName: key, agents: agents);
}).AddAsAIAgent();

var scienceConcurrentWorkflow = builder.AddWorkflow("science-concurrent-workflow", (sp, key) =>
{
    List<IHostedAgentBuilder> usedAgents = [chemistryAgent, mathsAgent, literatureAgent];
    var agents = usedAgents.Select(ab => sp.GetRequiredKeyedService<AIAgent>(ab.Name));
    return AgentWorkflowBuilder.BuildConcurrent(workflowName: key, agents: agents);
}).AddAsAIAgent();

builder.AddOpenAIChatCompletions();
builder.AddOpenAIResponses();

var app = builder.Build();

app.MapOpenApi();
app.UseSwaggerUI(options => options.SwaggerEndpoint("/openapi/v1.json", "Agents API"));

// Configure the HTTP request pipeline.
app.UseExceptionHandler();

// attach a2a with simple message communication
app.MapA2A(pirateAgentBuilder, path: "/a2a/pirate");
app.MapA2A(knightsKnavesAgentBuilder, path: "/a2a/knights-and-knaves", agentCard: new()
{
    Name = "Knights and Knaves",
    Description = "An agent that helps you solve the knights and knaves puzzle.",
    Version = "1.0",

    // Url can be not set, and SDK will help assign it.
    // Url = "http://localhost:5390/a2a/knights-and-knaves"
});

app.MapOpenAIResponses();

app.MapOpenAIChatCompletions(pirateAgentBuilder);
app.MapOpenAIChatCompletions(knightsKnavesAgentBuilder);

// Map the agents HTTP endpoints
app.MapAgentDiscovery("/agents");

app.MapDefaultEndpoints();
app.Run();
