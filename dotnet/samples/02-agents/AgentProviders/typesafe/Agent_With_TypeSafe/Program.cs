// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Jev, the TypeSafe System One model, as an IChatClient and as an AIAgent.
// Jev does not write text: it answers typed questions about the conversation and returns calibrated probabilities.

using System.ClientModel;
using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.TypeSafe;
using Microsoft.Extensions.AI;

var apiKey = Environment.GetEnvironmentVariable("TYPESAFE_API_KEY") ?? throw new InvalidOperationException("TYPESAFE_API_KEY is not set.");

// 1. The questions to answer. Each answer comes back under the ID of its question.
Dictionary<string, JevQuestion> questions = new()
{
    ["department"] = new JevChoiceQuestion
    {
        Instructions = "Which team should handle the support request?",
        Criteria = new Dictionary<string, JevEntry>
        {
            ["billing"] = "Payments, subscriptions, invoices, or refunds",
            ["technical"] = "Bugs, outages, integrations, or account access",
            ["sales"] = "Pricing, upgrades, or new account questions",
        },
    },
    ["frustration"] = new JevScoreQuestion
    {
        Instructions = "How frustrated does the customer appear?",
        Criteria = ["Calm and factual", "Frustrated but civil", "Very angry or threatening to leave"],
    },
    ["is_urgent"] = new JevNoulQuestion
    {
        Instructions = "Does the request require urgent attention?",
        Criteria = new JevNoulCriteria
        {
            True = "The customer describes ongoing harm, lost revenue, or an immediate deadline",
            False = "The request can wait for the normal support queue",
        },
    },
};

// 2. Call the chat client directly. WithJevQuestions passes the questions through ChatOptions.
using IChatClient chatClient = new JevChatClient(new ApiKeyCredential(apiKey));
ChatResponse direct = await chatClient.GetResponseAsync(
    "I was charged twice for the same subscription. Please refund the duplicate charge.",
    new ChatOptions().WithJevQuestions(questions));
PrintEvaluation("Direct JevChatClient result:", direct.GetJevResult()!);

// 3. Use the same client through an agent. ChatClientAgentRunOptions carries the questions for one run.
AIAgent agent = chatClient.AsAIAgent(name: "JevTicketEvaluator", instructions: "Evaluate the support request.");
AgentResponse agentResponse = await agent.RunAsync(
    "Our checkout integration has failed for three days and we are losing sales. Please help ASAP.",
    options: new ChatClientAgentRunOptions(new ChatOptions().WithJevQuestions(questions)));
PrintEvaluation("Agent result:", agentResponse.GetJevResult()!);

// 4. Default questions. A client created with DefaultQuestions answers requests that pass no questions, so code that
// knows nothing about Jev can use it like any other IChatClient; here, an agent run without Jev options.
using IChatClient triageClient = new JevChatClient(new ApiKeyCredential(apiKey), new JevChatClientOptions { DefaultQuestions = questions });
AgentResponse triaged = await triageClient.AsAIAgent(name: "JevTriage").RunAsync(
    "Hi, could you send me a copy of last month's invoice when you get a chance? Thanks!");
PrintEvaluation("Default questions result:", triaged.GetJevResult()!);

// 5. Function calling. Jev cannot write arguments, so it chooses them from closed sets: an enum, a Boolean, and an
// optional enum that is passed only when Jev decides the user asked for it. The user asks about two cities, so the
// client allows two tool calls per turn instead of the default one. Jev reads the tool's name and description when
// it chooses a tool, so the local function gets a readable name instead of its compiler-generated one.
using IChatClient weatherClient = new JevChatClient(new ApiKeyCredential(apiKey), new JevChatClientOptions { MaximumToolCallsPerTurn = 2 });
AIAgent weatherAgent = weatherClient.AsAIAgent(name: "WeatherEvaluator", tools: [AIFunctionFactory.Create(GetWeather, "get_weather")]);
var comparison = new Dictionary<string, JevQuestion>
{
    ["better_city"] = new JevChoiceQuestion
    {
        Instructions = "Which city has better weather based on the tool results?",
        Criteria = new Dictionary<string, JevEntry>
        {
            ["Seattle"] = "Seattle has the better weather.",
            ["Amsterdam"] = "Amsterdam has the better weather.",
        },
    },
};
AgentResponse weather = await weatherAgent.RunAsync(
    "Give me a detailed weather report for Seattle and Amsterdam in Fahrenheit and tell me where the weather is better.",
    options: new ChatClientAgentRunOptions(new ChatOptions().WithJevQuestions(comparison)));

// After tool calls, the text is the tool results followed by one line per Choice and Score answer.
Console.WriteLine("\nFunction calling result:");
Console.WriteLine(weather.Text);
Console.WriteLine($"Comparison confidence: {((JevChoiceResponse)weather.GetJevResult()!.Answers["better_city"]).Confidence:F3}");

// 6. Tool approval. A tool wrapped in ApprovalRequiredAIFunction runs only after the user approves the call that Jev
// chose. The session keeps the pending call, so the approval is sent in a second run with the same questions.
AIAgent refundAgent = chatClient.AsAIAgent(name: "RefundAgent", tools: [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(IssueRefund, "issue_refund"))]);
AgentSession session = await refundAgent.CreateSessionAsync();
var refundOptions = new ChatClientAgentRunOptions(new ChatOptions().WithJevQuestions(questions));
AgentResponse refund = await refundAgent.RunAsync(
    "I was charged twice for my Pro plan this month. Please refund the duplicate charge.",
    session,
    refundOptions);

Console.WriteLine("\nTool approval:");
if (refund.Messages.SelectMany(message => message.Contents).OfType<ToolApprovalRequestContent>().FirstOrDefault() is { ToolCall: FunctionCallContent call } approval)
{
    string arguments = string.Join(", ", call.Arguments?.Select(argument => $"{argument.Key}: {argument.Value}") ?? []);
    Console.Write($"Jev wants to call {call.Name}({arguments}). Approve? (Y/N): ");
    bool approved = Console.ReadLine()?.Trim().Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
    refund = await refundAgent.RunAsync(new ChatMessage(ChatRole.User, [approval.CreateResponse(approved)]), session, refundOptions);
}

Console.WriteLine(refund.Text);

static void PrintEvaluation(string label, JevResult result)
{
    var department = (JevChoiceResponse)result.Answers["department"];
    var frustration = (JevScoreResponse)result.Answers["frustration"];
    var urgent = (JevNoulResponse)result.Answers["is_urgent"];

    Console.WriteLine($"\n{label}");
    Console.WriteLine($"Department: {department.Choice} (confidence {department.Confidence:F3})");
    Console.WriteLine($"Frustration score: {frustration.Score:F3} of {frustration.Legend.Count - 1}");
    Console.WriteLine($"Urgency probability: {urgent.Noul:F3}");
    Console.WriteLine($"Tokens: {result.Usage.InputTokens} in, {result.Usage.OutputTokens} out");
}

[Description("Gets the weather forecast.")]
static string GetWeather(
    [Description("The city to get the weather for")] City city,
    [Description("Whether to include a detailed hourly forecast; true when the user asks for a detailed report")] bool detailed,
    [Description("The temperature unit; leave it out to use Celsius")] TemperatureUnit? unit = null)
{
    int celsius = Random.Shared.Next(15, 31);
    string temperature = unit == TemperatureUnit.Fahrenheit ? $"{(celsius * 9 / 5) + 32} F" : $"{celsius} C";
    string suffix = detailed ? " with a detailed hourly forecast" : string.Empty;
    return $"{city} is sunny and {temperature}{suffix}.";
}

[Description("Refunds a duplicate charge for a subscription plan.")]
static string IssueRefund([Description("The plan that was charged twice")] Plan plan) =>
    $"Refunded the duplicate {plan} plan charge.";

internal enum City
{
    Seattle,
    Amsterdam,
    Paris,
}

internal enum TemperatureUnit
{
    Celsius,
    Fahrenheit,
}

internal enum Plan
{
    Basic,
    Pro,
    Enterprise,
}
