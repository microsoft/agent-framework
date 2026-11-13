// Copyright (c) Microsoft. All rights reserved.

// This sample gives a Foundry agent a decision as a tool, with the decision API proposed for Microsoft.Extensions.AI.
// The application fixes the questions in a typed DecisionDefinition, and the agent only passes the ticket: Jev, the
// TypeSafe System One model, answers the questions, and the agent replies from the typed result. The same tool is then
// answered by a local IDecisionClient, without changing the agent.

#pragma warning disable MEAI001 // The decision API is experimental.

using System.ClientModel;
using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.TypeSafe;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var typeSafeApiKey = Environment.GetEnvironmentVariable("TYPESAFE_API_KEY") ?? throw new InvalidOperationException("TYPESAFE_API_KEY is not set.");

// <definition>
// 1. The questions, as a typed result. The enum property is a Choice among its values, the probability is a Binary
// question, and the frustration is a Score on an ordered rubric. The [Description] attributes on TicketAnalysis and
// Department, at the end of this file, are the question instructions and the choice descriptions.
DecisionDefinition<TicketAnalysis> analysis = DecisionDefinition<TicketAnalysis>.Create(builder =>
{
    builder.Choice(result => result.Department);
    builder.BinaryProbability(result => result.UrgentProbability);
    builder.Score(result => result.Frustration, [new("calm", "The customer is calm."), new("annoyed", "The customer is annoyed."), new("angry", "The customer is angry.")]);
});
// </definition>

// <tool>
// 2. The tool. Its only argument is the ticket. The questions and the decision client belong to the application, so
// the model cannot change what is asked, and the result is the typed TicketAnalysis.
var toolOptions = new AIFunctionFactoryOptions
{
    Name = "analyze_ticket",
    Description = "Classifies a support ticket: the department that should handle it, the probability that it is urgent, and how frustrated the customer is.",
};

using IDecisionClient jev = new JevDecisionClient(new ApiKeyCredential(typeSafeApiKey));
AIFunction analyzeTicket = analysis.AsAIFunction<SupportTicket>(jev, toolOptions);
// </tool>

const string Instructions = """
    You triage customer support tickets. For each ticket, call analyze_ticket with the ticket text, then reply in one
    line with the department, whether the ticket is urgent (when the urgent probability is above 0.5), and the
    frustration level (0 is calm, 1 annoyed, 2 angry).
    """;

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var projectClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());
AIAgent agent = projectClient.AsAIAgent(model: deploymentName, instructions: Instructions, name: "TicketTriage", tools: [analyzeTicket]);

string[] tickets =
[
    "I've been trying to connect my Stripe account for 3 days and the integration keeps failing. I'm losing sales. Please help ASAP.",
    "Hi, could you send me a copy of last month's invoice when you get a chance? Thanks!",
];

foreach (string ticket in tickets)
{
    await TriageAsync(agent, ticket);
}

// <local_client>
// 3. The same definition and agent instructions, answered by another decision client. Any IDecisionClient works,
// such as another decision model or, here, a local keyword matcher.
using IDecisionClient keywords = new KeywordDecisionClient();
AIAgent localAgent = projectClient.AsAIAgent(
    model: deploymentName,
    instructions: Instructions,
    name: "LocalTicketTriage",
    tools: [analysis.AsAIFunction<SupportTicket>(keywords, toolOptions)]);
// </local_client>

Console.WriteLine("The same tool, answered by a local keyword decision client:");
Console.WriteLine();
await TriageAsync(localAgent, tickets[1]);

static async Task TriageAsync(AIAgent agent, string ticket)
{
    AgentResponse response = await agent.RunAsync(ticket);

    Console.WriteLine($"Ticket: {ticket}");
    foreach (FunctionResultContent result in response.Messages.SelectMany(static m => m.Contents).OfType<FunctionResultContent>())
    {
        Console.WriteLine($"Tool result: {result.Result}");
    }

    Console.WriteLine($"Agent: {response.Text}");
    Console.WriteLine();
}

#pragma warning disable CA1812 // SupportTicket is the tool argument, and TicketAnalysis is created from the answers.

/// <summary>The tool's input: the ticket that the agent passes.</summary>
internal sealed record SupportTicket([Description("The ticket text, as the customer wrote it.")] string Text);

/// <summary>The teams that handle tickets. Each description tells the decision model what belongs to the team.</summary>
internal enum Department
{
    [Description("Payments, invoices, refunds, and charges.")]
    Billing,

    [Description("Bugs, outages, errors, and integrations.")]
    Technical,

    [Description("Plans, pricing, upgrades, and new purchases.")]
    Sales,
}

/// <summary>The tool's result. Each description is the instruction of the question that fills the property.</summary>
internal sealed record TicketAnalysis(
    [Description("Which team should handle the ticket?")] Department Department,
    [Description("Does the ticket need urgent attention?")] double UrgentProbability,
    [Description("How frustrated is the customer who wrote the ticket?")] double Frustration);
#pragma warning restore CA1812
