// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Hosting.UnitTests;

public class AgentProxyThreadTests
{
    /// <summary>
    /// Provides valid identifier values that conform to RFC 3986 unreserved characters.
    /// </summary>
    public static IEnumerable<object[]> ValidIds { get; } =
        [
            ["normal"],
            ["test-id"],
            ["test_id"],
            ["test.id"],
            ["test~id"],
            ["ABC123"],
            ["a"],
            ["123"],
            ["test-id_with.various~chars"],
            [new string('a', 100)] // Long but valid ID
        ];

    /// <summary>
    /// Provides invalid identifier values that violate the RFC 3986 unreserved character rules.
    /// </summary>
    public static IEnumerable<object[]> InvalidIds { get; } =
        [
            [" "], // Space not allowed
            ["!@#$%^&*()"], // Special characters not allowed
            ["test id"], // Space not allowed
            ["test/id"], // Forward slash not allowed
            ["test?id"], // Question mark not allowed
            ["test#id"], // Hash not allowed
            ["test@id"], // At symbol not allowed
            ["test id with spaces"], // Multiple spaces not allowed
            ["test\tid"], // Tab not allowed
            ["test\nid"], // Newline not allowed
        ];

    /// <summary>
    /// Verifies that providing valid id to <see cref="AgentProxyThread"/> constructor sets the Id property correctly.
    /// </summary>
    /// <param name="id">The valid identifier to test.</param>
    [Theory]
    [MemberData(nameof(ValidIds))]
    public void Constructor_ValidId_SetsIdProperty(string id)
    {
        // Act
        var thread = new AgentProxyThread(id);

        // Assert
        Assert.Equal(id, thread.ConversationId);
    }

    /// <summary>
    /// Verifies that providing invalid id to <see cref="AgentProxyThread"/> constructor throws an <see cref="ArgumentException"/>.
    /// </summary>
    /// <param name="id">The invalid identifier to test.</param>
    [Theory]
    [MemberData(nameof(InvalidIds))]
    public void Constructor_InvalidId_ThrowsArgumentException(string id)
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => new AgentProxyThread(id));
        Assert.Contains("Thread ID", exception.Message);
        Assert.Contains("alphanumeric characters, hyphens, underscores, dots, and tildes", exception.Message);
    }

    /// <summary>
    /// Verifies that providing a null id to <see cref="AgentProxyThread"/> constructor throws an <see cref="ArgumentNullException"/>.
    /// </summary>
    [Fact]
    public void Constructor_NullId_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentProxyThread(null!));

    /// <summary>
    /// Verifies that providing an empty id to <see cref="AgentProxyThread"/> constructor throws an <see cref="ArgumentException"/>.
    /// </summary>
    [Fact]
    public void Constructor_EmptyId_ThrowsArgumentException() =>
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentProxyThread(""));

    /// <summary>
    /// Verifies that the default constructor initializes the Id property with a valid non-empty GUID string in "N" format.
    /// </summary>
    [Fact]
    public void Constructor_Default_AssignsValidGuidStringAsId()
    {
        // Arrange & Act
        var thread = new AgentProxyThread();

        // Assert
        Assert.False(string.IsNullOrEmpty(thread.ConversationId));
        Assert.True(Guid.TryParseExact(thread.ConversationId, "N", out _), $"Id '{thread.ConversationId}' is not a valid GUID in 'N' format.");
    }

    /// <summary>
    /// Verifies that successive default constructors produce unique Id values.
    /// </summary>
    [Fact]
    public void Constructor_Default_CreatesUniqueIds()
    {
        // Arrange & Act
        var thread1 = new AgentProxyThread();
        var thread2 = new AgentProxyThread();

        // Assert
        Assert.NotEqual(thread1.ConversationId, thread2.ConversationId);
    }

    /// <summary>
    /// Verifies that CreateId returns a non-null, non-empty 32-character hexadecimal string without dashes.
    /// </summary>
    [Fact]
    public void CreateId_ReturnsValidHexString()
    {
        // Arrange & Act
        string id = AgentProxyThread.CreateId();

        // Assert
        Assert.False(string.IsNullOrEmpty(id));
        Assert.Equal(32, id.Length);
        Assert.Matches("^[0-9a-f]{32}$", id);
    }

    /// <summary>
    /// Verifies that multiple calls to CreateId produce unique identifiers.
    /// </summary>
    [Fact]
    public void CreateId_MultipleCalls_ReturnUniqueValues()
    {
        // Arrange & Act
        string id1 = AgentProxyThread.CreateId();
        string id2 = AgentProxyThread.CreateId();

        // Assert
        Assert.NotEqual(id1, id2);
    }

    /// <summary>
    /// Verifies that ManyCallsInParallel produces unique values across many calls.
    /// </summary>
    [Fact]
    public void CreateId_ManyCallsInParallel_AllUnique()
    {
        // Arrange
        const int NumberOfIds = 1000;
        var ids = new string[NumberOfIds];

        // Act - Create IDs in parallel to test thread safety
        Parallel.For(0, NumberOfIds, i => ids[i] = AgentProxyThread.CreateId());

        // Assert
        var uniqueIds = ids.Distinct().Count();
        Assert.Equal(NumberOfIds, uniqueIds);
    }

    /// <summary>
    /// Verifies that CreateId generates IDs that pass validation.
    /// </summary>
    [Fact]
    public void CreateId_GeneratesValidIds()
    {
        // Arrange & Act
        for (int i = 0; i < 100; i++)
        {
            string id = AgentProxyThread.CreateId();

            // Assert - Should not throw exception
            var thread = new AgentProxyThread(id);
            Assert.Equal(id, thread.ConversationId);
        }
    }

    /// <summary>
    /// Verifies specific edge cases for valid IDs.
    /// </summary>
    [Theory]
    [InlineData("a")]
    [InlineData("1")]
    [InlineData("_")]
    [InlineData("-")]
    [InlineData(".")]
    [InlineData("~")]
    [InlineData("a1")]
    [InlineData("test-123")]
    [InlineData("my_thread.id~1")]
    public void Constructor_ValidIdEdgeCases_SetsIdProperty(string id)
    {
        // Act
        var thread = new AgentProxyThread(id);

        // Assert
        Assert.Equal(id, thread.ConversationId);
    }

    /// <summary>
    /// Verifies specific edge cases for invalid IDs.
    /// </summary>
    [Theory]
    [InlineData(" leading-space")]
    [InlineData("trailing-space ")]
    [InlineData("with spaces")]
    [InlineData("with\ttab")]
    [InlineData("with\nnewline")]
    [InlineData("with/slash")]
    [InlineData("with\\backslash")]
    [InlineData("with%percent")]
    [InlineData("with+plus")]
    [InlineData("with=equals")]
    [InlineData("with?question")]
    [InlineData("with#hash")]
    [InlineData("with@at")]
    [InlineData("with[bracket")]
    [InlineData("with]bracket")]
    [InlineData("with{brace")]
    [InlineData("with}brace")]
    [InlineData("with(paren")]
    [InlineData("with)paren")]
    [InlineData("with!exclamation")]
    [InlineData("with*asterisk")]
    [InlineData("with:colon")]
    [InlineData("with;semicolon")]
    [InlineData("with,comma")]
    [InlineData("with\"quote")]
    [InlineData("with'apostrophe")]
    public void Constructor_InvalidIdEdgeCases_ThrowsArgumentException(string id)
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => new AgentProxyThread(id));
        Assert.Contains("Thread ID", exception.Message);
    }

    /// <summary>
    /// Verifies that AgentProxyThread inherits from AgentThread.
    /// </summary>
    [Fact]
    public void AgentProxyThread_InheritsFromAgentThread()
    {
        // Arrange & Act
        var thread = new AgentProxyThread();

        // Assert
        Assert.IsType<AgentThread>(thread, exactMatch: false);
    }

    /// <summary>
    /// Verifies that Id property is accessible.
    /// </summary>
    [Fact]
    public void Id_IsAccessible()
    {
        // Arrange & Act
        var thread = new AgentProxyThread("test-id");

        // Assert
        Assert.NotNull(thread.ConversationId);
        Assert.Equal("test-id", thread.ConversationId);
    }

    /// <summary>
    /// Verifies that thread ID remains immutable after construction.
    /// </summary>
    [Fact]
    public void Id_IsImmutable()
    {
        // Arrange
        const string OriginalId = "immutable-id";
        var thread = new AgentProxyThread(OriginalId);

        // Act & Assert
        Assert.Equal(OriginalId, thread.ConversationId);
    }

    /// <summary>
    /// Verifies that default constructor creates thread with valid GUID format.
    /// </summary>
    [Fact]
    public void Constructor_Default_AlwaysCreatesValidGuid()
    {
        // Arrange & Act
        var thread = new AgentProxyThread();

        // Assert
        Assert.NotNull(thread.ConversationId);
        Assert.Equal(32, thread.ConversationId.Length);
        Assert.True(Guid.TryParseExact(thread.ConversationId, "N", out var guid));
        Assert.NotEqual(Guid.Empty, guid);
    }
}
