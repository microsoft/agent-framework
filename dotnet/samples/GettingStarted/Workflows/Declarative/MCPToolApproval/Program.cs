// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Agents.ToolApproval;

internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        IConfiguration configuration = Application.InitializeConfig();
        string foundryEndpoint = configuration.GetValue(Application.Settings.FoundryEndpoint);
        AgentsClient agentsClient = new(new Uri(foundryEndpoint), new AzureCliCredential());

        await agentsClient.CreateAgentAsync(
            agentName: "StudentAgent",
            agentDefinition: DefineStudentAgent(configuration),
            agentDescription: "Student agent for MathChat workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "TeacherAgent",
            agentDefinition: DefineTeacherAgent(configuration),
            agentDescription: "Teacher agent for MathChat workflow");
    }

    private static PromptAgentDefinition DefineStudentAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Your job is help a math teacher practice teaching by making intentional mistakes.
                You Attempt to solve the given math problem, but with intentional mistakes so the teacher can help.
                Always incorporate the teacher's advice to fix your next response.
                You have the math-skills of a 6th grader.
                Your job is help a math teacher practice teaching by making intentional mistakes.
                You Attempt to solve the given math problem, but with intentional mistakes so the teacher can help.
                Always incorporate the teacher's advice to fix your next response.
                You have the math-skills of a 6th grader.
                """
        };

    private static PromptAgentDefinition DefineTeacherAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Review and coach the student's approach to solving the given math problem.
                Don't repeat the solution or try and solve it.
                If the student has demonstrated comprehension and responded to all of your feedback,
                give the student your congraluations by using the word "congratulations".
                Review and coach the student's approach to solving the given math problem.
                Don't repeat the solution or try and solve it.
                If the student has demonstrated comprehension and responded to all of your feedback,
                give the student your congraluations by using the word "congratulations".
                """
        };
}
