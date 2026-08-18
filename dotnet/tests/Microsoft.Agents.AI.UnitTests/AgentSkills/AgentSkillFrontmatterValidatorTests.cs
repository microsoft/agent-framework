// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentSkillFrontmatter"/> validation.
/// </summary>
public sealed class AgentSkillFrontmatterValidatorTests
{
    [Theory]
    [InlineData("my-skill")]
    [InlineData("a")]
    [InlineData("skill123")]
    [InlineData("a1b2c3")]
    public void ValidateName_ValidName_ReturnsTrue(string name)
    {
        // Act
        bool result = AgentSkillFrontmatter.ValidateName(name, out string? reason);

        // Assert
        Assert.True(result);
        Assert.Null(reason);
    }

    [Theory]
    [InlineData("-leading-hyphen")]
    [InlineData("trailing-hyphen-")]
    [InlineData("has spaces")]
    [InlineData("UPPERCASE")]
    [InlineData("consecutive--hyphens")]
    [InlineData("special!chars")]
    public void ValidateName_InvalidName_ReturnsFalse(string name)
    {
        // Act
        bool result = AgentSkillFrontmatter.ValidateName(name, out string? reason);

        // Assert
        Assert.False(result);
        Assert.NotNull(reason);
        Assert.Contains("name", reason, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ValidateName_NameExceedsMaxLength_ReturnsFalse()
    {
        // Arrange
        string longName = new('a', 65);

        // Act
        bool result = AgentSkillFrontmatter.ValidateName(longName, out string? reason);

        // Assert
        Assert.False(result);
        Assert.NotNull(reason);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void ValidateName_NullOrWhitespace_ReturnsFalse(string? name)
    {
        // Act
        bool result = AgentSkillFrontmatter.ValidateName(name, out string? reason);

        // Assert
        Assert.False(result);
        Assert.NotNull(reason);
    }

    [Fact]
    public void ValidateDescription_ValidDescription_ReturnsTrue()
    {
        // Act
        bool result = AgentSkillFrontmatter.ValidateDescription("A valid description.", out string? reason);

        // Assert
        Assert.True(result);
        Assert.Null(reason);
    }

    [Fact]
    public void ValidateDescription_DescriptionExceedsMaxLength_ReturnsFalse()
    {
        // Arrange
        string longDesc = new('x', 1025);

        // Act
        bool result = AgentSkillFrontmatter.ValidateDescription(longDesc, out string? reason);

        // Assert
        Assert.False(result);
        Assert.NotNull(reason);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void ValidateDescription_NullOrWhitespace_ReturnsFalse(string? description)
    {
        // Act
        bool result = AgentSkillFrontmatter.ValidateDescription(description, out string? reason);

        // Assert
        Assert.False(result);
        Assert.NotNull(reason);
    }

    [Fact]
    public void ValidateCompatibility_Null_ReturnsTrue()
    {
        // Act
        bool result = AgentSkillFrontmatter.ValidateCompatibility(null, out string? reason);

        // Assert
        Assert.True(result);
        Assert.Null(reason);
    }

    [Fact]
    public void ValidateCompatibility_WithinMaxLength_ReturnsTrue()
    {
        // Arrange
        string compatibility = new('x', 500);

        // Act
        bool result = AgentSkillFrontmatter.ValidateCompatibility(compatibility, out string? reason);

        // Assert
        Assert.True(result);
        Assert.Null(reason);
    }

    [Fact]
    public void ValidateCompatibility_ExceedsMaxLength_ReturnsFalse()
    {
        // Arrange
        string compatibility = new('x', 501);

        // Act
        bool result = AgentSkillFrontmatter.ValidateCompatibility(compatibility, out string? reason);

        // Assert
        Assert.False(result);
        Assert.NotNull(reason);
    }

    [Theory]
    [InlineData("UPPERCASE")]
    [InlineData("-leading")]
    [InlineData("trailing-")]
    [InlineData("consecutive--hyphens")]
    public void Constructor_InvalidName_ThrowsArgumentException(string name)
    {
        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new AgentSkillFrontmatter(name, "A valid description."));
        Assert.Contains("name", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Constructor_NameExceedsMaxLength_ThrowsArgumentException()
    {
        // Arrange
        string longName = new('a', 65);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentSkillFrontmatter(longName, "A valid description."));
    }

    [Fact]
    public void Constructor_DescriptionExceedsMaxLength_ThrowsArgumentException()
    {
        // Arrange
        string longDesc = new('x', 1025);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentSkillFrontmatter("valid-name", longDesc));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_NullOrWhitespaceName_ThrowsArgumentException(string? name)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentSkillFrontmatter(name!, "A valid description."));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_NullOrWhitespaceDescription_ThrowsArgumentException(string? description)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentSkillFrontmatter("valid-name", description!));
    }

    [Fact]
    public void Compatibility_ExceedsMaxLength_ThrowsArgumentException()
    {
        // Arrange
        var frontmatter = new AgentSkillFrontmatter("valid-name", "A valid description.");
        string longCompatibility = new('x', 501);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => frontmatter.Compatibility = longCompatibility);
    }

    [Fact]
    public void Compatibility_WithinMaxLength_Succeeds()
    {
        // Arrange
        var frontmatter = new AgentSkillFrontmatter("valid-name", "A valid description.");
        string compatibility = new('x', 500);

        // Act
        frontmatter.Compatibility = compatibility;

        // Assert
        Assert.Equal(compatibility, frontmatter.Compatibility);
    }

    [Fact]
    public void Compatibility_Null_Succeeds()
    {
        // Arrange
        var frontmatter = new AgentSkillFrontmatter("valid-name", "A valid description.");

        // Act
        frontmatter.Compatibility = null;

        // Assert
        Assert.Null(frontmatter.Compatibility);
    }

    [Fact]
    public void Constructor_WithCompatibility_SetsValue()
    {
        // Arrange & Act
        var frontmatter = new AgentSkillFrontmatter("valid-name", "A valid description.", "Requires Python 3.10+");

        // Assert
        Assert.Equal("Requires Python 3.10+", frontmatter.Compatibility);
    }

    [Fact]
    public void Constructor_CompatibilityExceedsMaxLength_ThrowsArgumentException()
    {
        // Arrange
        string longCompatibility = new('x', 501);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentSkillFrontmatter("valid-name", "A valid description.", longCompatibility));
    }
}
