// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;

public sealed class Testcase
{
    [JsonConstructor]
    public Testcase(string description, TestcaseSetup setup, TestcaseValidation validation)
    {
        this.Description = description;
        this.Setup = setup;
        this.Validation = validation;
    }

    public string Description { get; }

    public TestcaseSetup Setup { get; }

    public TestcaseValidation Validation { get; }
}

public sealed class TestcaseSetup
{
    [JsonConstructor]
    public TestcaseSetup(TestcaseInput input)
    {
        this.Input = input;
    }
    public TestcaseInput Input { get; }
    public IList<TestcaseInput> Responses { get; init; } = [];
}

public sealed class TestcaseInput
{
    [JsonConstructor]
    public TestcaseInput(string type, string value)
    {
        this.Type = type;
        this.Value = value;
    }

    public string Type { get; }
    public string Value { get; }
}

public sealed class TestcaseValidation
{
    [JsonConstructor]
    public TestcaseValidation(int conversationCount, int minActionCount, int minResponseCount)
    {
        this.ConversationCount = conversationCount;
        this.MinActionCount = minActionCount;
        this.MinResponseCount = minResponseCount;
    }

    public TestcaseValidationActions Actions { get; init; } = TestcaseValidationActions.Empty;
    public int ConversationCount { get; }
    public int MinActionCount { get; }
    // Default expectation is MinActionCount when not defined
    public int? MaxActionCount { get; init; }
    // Default expectation is MinResponseCount when not defined
    public int? MinMessageCount { get; init; }
    // Default expectation is MaxResponseCount when not defined
    public int? MaxMessageCount { get; init; }
    public int MinResponseCount { get; }
    // Default expectation is MinResponseCount when not defined
    public int? MaxResponseCount { get; init; }
}

public sealed class TestcaseValidationActions
{
    public static TestcaseValidationActions Empty { get; } = new([]);

    [JsonConstructor]
    public TestcaseValidationActions(IList<string> start)
    {
        this.Start = start;
    }

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public IList<string> Start { get; }

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public IList<string> Repeat { get; init; } = [];

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public IList<string> Final { get; init; } = [];
}
