// Copyright (c) Microsoft. All rights reserved.

namespace VerifySamples;

/// <summary>
/// Defines the expected behavior for each sample in 01-get-started.
/// </summary>
internal static class GetStartedSamples
{
    public static IReadOnlyList<SampleDefinition> All { get; } =
    [
        new SampleDefinition
        {
            Name = "05_first_workflow",
            ProjectPath = "samples/01-get-started/05_first_workflow",
            RequiredEnvironmentVariables = [],
            IsDeterministic = true,
            MustContain =
            [
                "UppercaseExecutor: HELLO, WORLD!",
                "ReverseTextExecutor: !DLROW ,OLLEH",
            ],
        },

        new SampleDefinition
        {
            Name = "01_hello_agent",
            ProjectPath = "samples/01-get-started/01_hello_agent",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "There should be two separate joke responses — one from a non-streaming call and one from a streaming call.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "02_add_tools",
            ProjectPath = "samples/01-get-started/02_add_tools",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain = [],
            ExpectedOutputDescription =
            [
                "The output should contain information about the weather in Amsterdam.",
                "The response should mention that it is cloudy with a high of 15°C (or equivalent), since this comes from a tool that returns a canned response.",
                "There should be two responses — one from a non-streaming call and one from a streaming call.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "03_multi_turn",
            ProjectPath = "samples/01-get-started/03_multi_turn",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "After the initial joke, there should be a modified version that includes emojis and is told in the voice of a pirate's parrot.",
                "The pattern repeats: first a non-streaming pirate joke + parrot version, then a streaming pirate joke + parrot version.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "04_memory",
            ProjectPath = "samples/01-get-started/04_memory",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain =
            [
                ">> Use session with blank memory",
                ">> Use deserialized session with previously created memories",
                ">> Read memories using memory component",
                "MEMORY - User Name:",
                "MEMORY - User Age:",
                ">> Use new session with previously created memories",
            ],
            ExpectedOutputDescription =
            [
                "In the 'Use session with blank memory' section, the agent should respond to the user's messages. It may ask for the user's name or age if not yet known.",
                "In the 'Use deserialized session with previously created memories' section, the agent should correctly recall that the user's name is Ruaidhrí and age is 20.",
                "The 'MEMORY - User Name:' line should show 'Ruaidhrí' (or a close transliteration).",
                "The 'MEMORY - User Age:' line should show '20'.",
                "In the 'Use new session with previously created memories' section, the agent should know the user's name and age from the transferred memory.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "06_host_your_agent",
            ProjectPath = "samples/01-get-started/06_host_your_agent",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "Requires Azure Functions Core Tools runtime and starts a web server.",
        },
    ];
}
