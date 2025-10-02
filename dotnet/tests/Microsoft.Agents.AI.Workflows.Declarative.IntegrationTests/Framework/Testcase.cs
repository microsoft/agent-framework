// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;

public sealed class Testcase
{
    [JsonConstructor]
    public Testcase(
        string description,
        TestcaseSetup setup,
        TestcaseValidation validation)
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
    public TestcaseValidation(int conversationCount, int minActionCount, int? maxActionCount = null, TestcaseValidationActions? actions = null)
    {
        this.ConversationCount = conversationCount;
        this.MinActionCount = minActionCount;
        this.MaxActionCount = maxActionCount;
        this.Actions = actions ?? new TestcaseValidationActions([]);
    }

    public TestcaseValidationActions Actions { get; }
    public int ConversationCount { get; }
    public int MinActionCount { get; }
    public int? MaxActionCount { get; }
}

public sealed class TestcaseValidationActions
{
    [JsonConstructor]
    public TestcaseValidationActions(IList<string> start, IList<string>? repeat = null, IList<string>? final = null)
    {
        this.Start = start;
        this.Repeat = repeat ?? [];
        this.Final = final ?? [];
    }

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public IList<string> Start { get; }

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public IList<string> Repeat { get; }

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public IList<string> Final { get; }
}
