// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

internal sealed class MathChatAgentProvider(IConfiguration configuration) : AgentProvider(configuration)
{
    protected override async IAsyncEnumerable<AgentVersion> CreateAgentsAsync(Uri foundryEndpoint)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        yield return
            await aiProjectClient.CreateAgentAsync(
                agentName: "StudentAgent",
                agentDefinition: this.DefineStudentAgent(),
                agentDescription: "Student agent for MathChat workflow");

        yield return
            await aiProjectClient.CreateAgentAsync(
                agentName: "TeacherAgent",
                agentDefinition: this.DefineTeacherAgent(),
                agentDescription: "Teacher agent for MathChat workflow");
    }

    private PromptAgentDefinition DefineStudentAgent() =>
        new(this.GetSetting(Settings.FoundryModelMini))
        {
            Instructions =
                """
                Your job is help a math teacher practice teaching by making intentional mistakes.
                You attempt to solve the given math problem, but with intentional mistakes so the teacher can help.
                Always incorporate the teacher's advice to fix your next response.
                You have the math-skills of a 6th grader.
                """
        };

    private PromptAgentDefinition DefineTeacherAgent() =>
        new(this.GetSetting(Settings.FoundryModelMini))
        {
            Instructions =
                """
                Review and coach the student's approach to solving the given math problem.
                Don't repeat the solution or try and solve it.
                If the student has demonstrated comprehension and responded to all of your feedback,
                give the student your congratulations by using the word "congratulations".
                """
        };
}
