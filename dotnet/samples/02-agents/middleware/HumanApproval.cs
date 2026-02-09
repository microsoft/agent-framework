// Copyright (c) Microsoft. All rights reserved.

// Human Approval Middleware
// Agent-level middleware that intercepts function approval requests and prompts
// the user for consent before allowing sensitive function invocations.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/middleware

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// <human_approval_middleware>
async Task<AgentResponse> ConsoleApprovalMiddleware(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    AgentResponse response = await innerAgent.RunAsync(messages, session, options, cancellationToken);

    List<FunctionApprovalRequestContent> approvalRequests = response.Messages
        .SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();

    while (approvalRequests.Count > 0)
    {
        response.Messages = approvalRequests
            .ConvertAll(req =>
            {
                Console.WriteLine($"Approve function '{req.FunctionCall.Name}'? (Y/N):");
                return new ChatMessage(ChatRole.User, [req.CreateResponse(
                    Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false)]);
            });

        response = await innerAgent.RunAsync(response.Messages, session, options, cancellationToken);
        approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();
    }

    return response;
}
// </human_approval_middleware>

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .BuildAIAgent(
        instructions: "You are a helpful assistant.",
        tools: [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(GetWeather))]);

var approvalAgent = agent
    .AsBuilder()
    .Use(ConsoleApprovalMiddleware, null)
    .Build();

Console.WriteLine(await approvalAgent.RunAsync("What's the weather in Seattle?"));
