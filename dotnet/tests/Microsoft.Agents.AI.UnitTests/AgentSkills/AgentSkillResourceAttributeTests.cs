// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentSkillResourceAttribute"/>.
/// </summary>
public sealed class AgentSkillResourceAttributeTests
{
    [Fact]
    public void DefaultConstructor_NameIsNull()
    {
        // Arrange & Act
        var attr = new AgentSkillResourceAttribute();

        // Assert
        Assert.Null(attr.Name);
    }

    [Fact]
    public void NamedConstructor_SetsName()
    {
        // Arrange & Act
        var attr = new AgentSkillResourceAttribute("my-resource");

        // Assert
        Assert.Equal("my-resource", attr.Name);
    }
}
