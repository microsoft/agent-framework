// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.Tests;

public class TopicIdTests
{
    [Fact]
    public void ConstrWithTypeOnlyTest()
    {
        // Arrange & Act
        TopicId topicId = new("testtype");

        // Assert
        Assert.Equal("testtype", topicId.Type);
    }

    [Fact]
    public void ConstructWithTypeAndSourceTest()
    {
        // Arrange & Act
        TopicId topicId = new("testtype", "customsource");

        // Assert
        Assert.Equal("testtype", topicId.Type);
        Assert.Equal("customsource", topicId.Source);
    }

    [Theory]
    [InlineData("testtype/https://github.com/cloudevents", "testtype", "https://github.com/cloudevents")]
    [InlineData("testtype/mailto:cncf-wg-serverless@lists.cncf.io", "testtype", "mailto:cncf-wg-serverless@lists.cncf.io")]
    [InlineData("testtype/urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66", "testtype", "urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66")]
    [InlineData("testtype//cloudevents/spec/pull/123", "testtype", "/cloudevents/spec/pull/123")]
    [InlineData("testtype//sensors/tn-1234567/alerts", "testtype", "/sensors/tn-1234567/alerts")]
    [InlineData("testtype/1-555-123-4567", "testtype", "1-555-123-4567")]
    public void ParseTest(string input, string expectedType, string expectedSource)
    {
        TopicId topicId = TopicId.Parse(input);

        Assert.Equal(expectedType, topicId.Type);
        Assert.Equal(expectedSource, topicId.Source);
    }

    [Theory]
    [InlineData("invalid-format")]
    [InlineData("")]
    public void InvalidFormatParseThrowsTest(string invalidInput)
    {
        // Act & Assert
        Assert.Throws<FormatException>(() => TopicId.Parse(invalidInput));
    }

    [Fact]
    public void ToStringTest()
    {
        // Arrange
        TopicId topicId = new("testtype", "customsource");

        // Act
        string result = topicId.ToString();

        // Assert
        Assert.Equal("testtype/customsource", result);
    }

    [Fact]
    public void EqualityTest()
    {
        // Arrange
        TopicId topicId1 = new("testtype", "customsource");
        TopicId topicId2 = new("testtype", "customsource");

        // Act & Assert
        Assert.True(topicId1.Equals(topicId2));
        Assert.True(topicId1.Equals((object)topicId2));
    }

    [Fact]
    public void InequalityTest()
    {
        // Arrange
        TopicId topicId1 = new("testtype1", "source1");
        TopicId topicId2 = new("testtype2", "source2");
        TopicId topicId3 = new("testtype1", "source2");
        TopicId topicId4 = new("testtype2", "source1");

        // Act & Assert
        Assert.False(topicId1.Equals(topicId2));
        Assert.False(topicId1.Equals(topicId3));
        Assert.False(topicId1.Equals(topicId4));
    }

    [Fact]
    public void NullEqualityTest()
    {
        // Arrange
        TopicId topicId = new("testtype", "customsource");

        // Act & Assert
        Assert.False(topicId.Equals(null));
    }

    [Fact]
    public void DifferentTypeEqualityTest()
    {
        // Arrange
        TopicId topicId = new("testtype", "customsource");
        const string DifferentType = "not-a-topic-id";

        // Act & Assert
        Assert.False(topicId.Equals(DifferentType));
    }

    [Fact]
    public void GetHashCodeTest()
    {
        // Arrange
        TopicId topicId1 = new("testtype", "customsource");
        TopicId topicId2 = new("testtype", "customsource");

        // Act
        int hash1 = topicId1.GetHashCode();
        int hash2 = topicId2.GetHashCode();

        // Assert
        Assert.Equal(hash1, hash2);
    }
}
