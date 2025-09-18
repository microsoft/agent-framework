// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use the <see cref="HandoffOrchestration"/> that represents
/// a customer support triage system.The orchestration consists of 4 agents, each specialized
/// in a different area of customer support: triage, refunds, order status, and order returns.
/// </summary>
public class HandoffOrchestration_Intro(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunOrchestrationAsync(bool streamedResponse)
    {
        // Define the agents & tools
        ChatClientAgent triageAgent =
            CreateAgent(
                instructions: "A customer support agent that triages issues.",
                name: "TriageAgent",
                description: "Handle customer requests.");
        ChatClientAgent statusAgent =
            CreateAgent(
                name: "OrderStatusAgent",
                instructions: "Handle order status requests.",
                description: "A customer support agent that checks order status.",
                functions: AIFunctionFactory.Create(OrderFunctions.CheckOrderStatus));
        ChatClientAgent returnAgent =
            CreateAgent(
                name: "OrderReturnAgent",
                instructions: "Handle order return requests.",
                description: "A customer support agent that handles order returns.",
                functions: AIFunctionFactory.Create(OrderFunctions.ProcessReturn));
        ChatClientAgent refundAgent =
            CreateAgent(
                name: "OrderRefundAgent",
                instructions: "Handle order refund requests.",
                description: "A customer support agent that handles order refund.",
                functions: AIFunctionFactory.Create(OrderFunctions.ProcessRefund));

        // Create a monitor to capturing agent responses (via ResponseCallback)
        // to display at the end of this sample. (optional)
        // NOTE: Create your own callback to capture responses in your application or service.
        OrchestrationMonitor monitor = new();
        // Define user responses for InteractiveCallback (since sample is not interactive)
        Queue<string> responses = new();
        const string Task = "I am a customer that needs help with my orders";
        responses.Enqueue("I'd like to track the status of my order");
        responses.Enqueue("My order ID is 123");
        responses.Enqueue("I want to return another order of mine");
        responses.Enqueue("Order ID 321");
        responses.Enqueue("Broken item");
        responses.Enqueue("No, bye");

        // Define the orchestration
        HandoffOrchestration orchestration =
            new(Handoffs
                    .StartWith(triageAgent)
                    .Add(triageAgent, [statusAgent, returnAgent, refundAgent])
                    .Add(statusAgent, triageAgent, "Transfer to this agent if the issue is not status related")
                    .Add(returnAgent, triageAgent, "Transfer to this agent if the issue is not return related")
                    .Add(refundAgent, triageAgent, "Transfer to this agent if the issue is not refund related"))
            {
                InteractiveCallback = () =>
                {
                    string text = responses.Dequeue();
                    ChatMessage input = new(ChatRole.User, text);
                    monitor.History.Add(input);
                    Console.WriteLine($"\n# INPUT: {input.Text}\n");
                    return new(input);
                },
                LoggerFactory = this.LoggerFactory,
                ResponseCallback = monitor.ResponseCallbackAsync,
                StreamingResponseCallback = streamedResponse ? monitor.StreamingResultCallbackAsync : null,
            };

        // Run the orchestration
        Console.WriteLine($"\n# INPUT:\n{Task}\n");
        AgentRunResponse result = await orchestration.RunAsync(Task);

        Console.WriteLine($"\n# RESULT: {result}");

        this.DisplayHistory(monitor.History);
    }

    private static class OrderFunctions
    {
        public static string CheckOrderStatus(string orderId) => $"Order {orderId} is shipped and will arrive in 2-3 days.";
        public static string ProcessReturn(string orderId, string reason) => $"Return for order {orderId} has been processed successfully.";
        public static string ProcessRefund(string orderId, string reason) => $"Refund for order {orderId} has been processed successfully.";
    }
}
