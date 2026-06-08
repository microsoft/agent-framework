// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentSkillScriptAttribute"/>.
/// </summary>
public sealed class AgentSkillScriptAttributeTests
{
    [Fact]
    public void DefaultConstructor_NameIsNull()
    {
        // Arrange & Act
        var attr = new AgentSkillScriptAttribute();

        // Assert
        Assert.Null(attr.Name);
    }

    [Fact]
    public void NamedConstructor_SetsName()
    {
        // Arrange & Act
        var attr = new AgentSkillScriptAttribute("my-script");

        // Assert
        Assert.Equal("my-script", attr.Name);
    }
}
