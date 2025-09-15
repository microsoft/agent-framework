// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

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
    public TestcaseValidation(int actionCount)
    {
        this.ActionCount = actionCount;
    }

    public int ActionCount { get; }
}
