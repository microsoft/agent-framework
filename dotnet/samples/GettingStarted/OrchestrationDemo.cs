// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents;
using Microsoft.Agents.Orchestration.Concurrent;
using Microsoft.Agents.Orchestration.GroupChat;
using Microsoft.Agents.Orchestration.Handoff;
using Microsoft.Extensions.AI;
using Microsoft.SemanticKernel.Agents.Runtime.InProcess;

namespace GettingStarted;

public class OrchestrationDemo(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Fact]
    public async Task RunConcurrentOrchestrationAsync()
    {
        // Define the agents
        Agent physicist =
            this.CreateResponsesAgent(
                instructions: "You are an expert in physics. You answer questions from a physics perspective.",
                description: "An expert in physics");
        Agent chemist =
            await this.CreateFoundryAgent(
                instructions: "You are an expert in chemistry. You answer questions from a chemistry perspective.",
                description: "An expert in chemistry");

        // Define the orchestration
        ConcurrentOrchestration orchestration = new(physicist, chemist);

        // Run the orchestration
        string[] output = await orchestration.RunToCompletionAsync("What is temperature?");
        Console.WriteLine(string.Join("\n\n", output.Select((x, i) => $"# RESULT[{i}]:\n\n{x}")));

        // Demo cleanup.
        await this.DeleteFoundryAgent(chemist.Id);
    }

    [Fact]
    public async Task RunConcurrentCodeReviewOrchestrationAsync()
    {
        // Define the agents
        Agent softwareDesigner =
            this.CreateResponsesAgent(
                instructions: "You are an expert in software design patterns. Your focus is improving software design.",
                description: "An expert in software design patterns");
        Agent styleCop =
            this.CreateGeminiAgent(
                instructions: "You are an expert in code style. Your focus is improving code formatting and styling.",
                description: "An expert in code style");
        Agent tester =
            await this.CreateFoundryAgent(
                instructions: "You are an expert software tester. Your focus is finding bugs in software.",
                description: "An expert software tester");

        // Define the orchestration
        ConcurrentOrchestration orchestration = new(softwareDesigner, styleCop, tester);

        // Run the orchestration
        var input = """
            ```csharp
            public class Stuff
            {
                public int Add(int x, int y) { return x + y;
                }

                public double Add2(double x, double y) { return x + y;
                }
            
                public double Multiply(double x, double y) { return x + y;
                }
                                }
            ```
            """;
        string[] output = await orchestration.RunToCompletionAsync($"Review the following code and output an improved version:\n{input}");
        Console.WriteLine(string.Join("\n\n", output.Select((x, i) => $"# RESULT[{i}]:\n\n{x}")));

        // Demo cleanup.
        await this.DeleteFoundryAgent(tester.Id);
    }

    [Fact]
    public async Task RunGroupChatBusinessProposalOrchestrationAsync()
    {
        // Define the agents
        Agent developer =
            this.CreateResponsesAgent(
                name: "Small Business Owner",
                instructions: "You are a small business owner trying to come up with ideas for improving your business.",
                description: "An expert in small business development");
        Agent reviewer =
            await this.CreateFoundryAgent(
                name: "Business Consultant",
                instructions: "You are an expert business consultant. You review business proposals and provide feedback to the owner based on your review. Provide specific suggestions for improvement. When you are happy with the proposal written by the owner reply with 'Approved' and output the Approved proposal.",
                description: "An expert business consultant");

        // Define the orchestration
        GroupChatOrchestration orchestration = new(
            new TerminationStringGroupChatManager("Approved") { MaximumInvocationCount = 8 },
            developer,
            reviewer)
        {
            ResponseCallback = this.WriteUpdatesToConsole
        };

        // Run the orchestration
        string output = await orchestration.RunToCompletionAsync("Produce a business proposal for a new type of chocolate that is low in sugar without compromising on taste.");
        Console.WriteLine($"# RESULT:\n\n{output}");

        // Demo cleanup.
        await this.DeleteFoundryAgent(reviewer.Id);
    }

    [Fact]
    public async Task RunHandoffOrchestrationAsync()
    {
        // Define the agents & tools
        ChatClientAgent triageAgent =
            this.CreateAgent(
                instructions: "A customer support agent that triages issues.",
                name: "TriageAgent",
                description: "Handle customer requests.");
        ChatClientAgent statusAgent =
            this.CreateAgent(
                name: "OrderStatusAgent",
                instructions: "Handle order status requests.",
                description: "A customer support agent that checks order status.",
                functions: AIFunctionFactory.Create(OrderFunctions.CheckOrderStatus));
        ChatClientAgent returnAgent =
            this.CreateAgent(
                name: "OrderReturnAgent",
                instructions: "Handle order return requests.",
                description: "A customer support agent that handles order returns.",
                functions: AIFunctionFactory.Create(OrderFunctions.ProcessReturn));
        ChatClientAgent refundAgent =
            this.CreateAgent(
                name: "OrderRefundAgent",
                instructions: "Handle order refund requests.",
                description: "A customer support agent that handles order refund.",
                functions: AIFunctionFactory.Create(OrderFunctions.ProcessRefund));

        // Define the orchestration
        HandoffOrchestration orchestration =
            new(OrchestrationHandoffs
                    .StartWith(triageAgent)
                    .Add(triageAgent, statusAgent, returnAgent, refundAgent)
                    .Add(statusAgent, triageAgent, "Transfer to this agent if the issue is not status related")
                    .Add(returnAgent, triageAgent, "Transfer to this agent if the issue is not return related")
                    .Add(refundAgent, triageAgent, "Transfer to this agent if the issue is not refund related"),
                triageAgent,
                statusAgent,
                returnAgent,
                refundAgent)
            {
                ResponseCallback = this.WriteUpdatesToConsole
            };

        // Run the orchestration
        string result = await orchestration.RunToCompletionAsync("I'd like to track the status of order 123 please");
        Console.WriteLine($"\n# RESULT: {result}");

        // Run the orchestration
        result = await orchestration.RunToCompletionAsync("I'd like to get a refund for order 123 please, since it arrived broken");
        Console.WriteLine($"\n# RESULT: {result}");
    }

    private static class OrderFunctions
    {
        public static string CheckOrderStatus(string orderId) => $"Order {orderId} is shipped and will arrive in 2-3 days.";
        public static string ProcessReturn(string orderId, string reason) => $"Return for order {orderId} has been processed successfully.";
        public static string ProcessRefund(string orderId, string reason) => $"Refund for order {orderId} has been processed successfully.";
    }

    private ValueTask WriteUpdatesToConsole(IEnumerable<ChatMessage> messages)
    {
        Console.WriteLine(string.Join(string.Empty, Enumerable.Repeat("-", 100)) + "\n# Update\n");
        Console.WriteLine(string.Join("\n\n", messages.Select((x, i) => $"## {x.AuthorName}:\n\n{x.Text}")));
        return ValueTask.CompletedTask;
    }
}
