// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentInlineSkillResource"/>.
/// </summary>
public sealed class AgentInlineSkillResourceTests
{
    [Fact]
    public async Task ReadAsync_StaticValue_ReturnsValueAsync()
    {
        // Arrange
        var resource = new AgentInlineSkillResource("config", "my-value");

        // Act
        var result = await resource.ReadAsync();

        // Assert
        Assert.Equal("my-value", result);
    }

    [Fact]
    public async Task ReadAsync_StaticObjectValue_ReturnsSameInstanceAsync()
    {
        // Arrange
        var obj = new object();
        var resource = new AgentInlineSkillResource("ref", obj);

        // Act
        var result = await resource.ReadAsync();

        // Assert
        Assert.Same(obj, result);
    }

    [Fact]
    public async Task ReadAsync_Delegate_InvokesFunctionAsync()
    {
        // Arrange
        int callCount = 0;
        var resource = new AgentInlineSkillResource("dynamic", () =>
        {
            callCount++;
            return "computed";
        });

        // Act
        var result = await resource.ReadAsync();

        // Assert
        Assert.Equal("computed", result?.ToString());
        Assert.Equal(1, callCount);
    }

    [Fact]
    public async Task ReadAsync_Delegate_InvokesEachTimeAsync()
    {
        // Arrange
        int callCount = 0;
        var resource = new AgentInlineSkillResource("counter", () => ++callCount);

        // Act
        await resource.ReadAsync();
        await resource.ReadAsync();
        var result = await resource.ReadAsync();

        // Assert
        Assert.Equal(3, callCount);
    }

    [Fact]
    public void Constructor_StaticValue_SetsNameAndDescription()
    {
        // Arrange & Act
        var resource = new AgentInlineSkillResource("my-res", "val", "A description.");

        // Assert
        Assert.Equal("my-res", resource.Name);
        Assert.Equal("A description.", resource.Description);
    }

    [Fact]
    public void Constructor_StaticValue_NullDescription_DescriptionIsNull()
    {
        // Arrange & Act
        var resource = new AgentInlineSkillResource("my-res", "val");

        // Assert
        Assert.Null(resource.Description);
    }

    [Fact]
    public void Constructor_StaticValue_NullValue_Throws()
    {
        // Act & Assert — cast needed to target the object overload
#pragma warning disable IDE0004
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkillResource("my-res", (object)null!));
#pragma warning restore IDE0004
    }

    [Fact]
    public void Constructor_Delegate_NullMethod_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkillResource("my-res", null!));
    }

    [Fact]
    public void Constructor_NullName_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkillResource(null!, "val"));
    }

    [Fact]
    public void Constructor_WhitespaceName_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() =>
            new AgentInlineSkillResource("  ", "val"));
    }

    [Fact]
    public void Constructor_Delegate_SetsNameAndDescription()
    {
        // Arrange & Act
        var resource = new AgentInlineSkillResource("dyn-res", () => "hello", "Dynamic resource.");

        // Assert
        Assert.Equal("dyn-res", resource.Name);
        Assert.Equal("Dynamic resource.", resource.Description);
    }

    [Fact]
    public async Task ReadAsync_WithSerializerOptions_SerializesReturnCustomTypeAsync()
    {
        // Arrange — delegate resource returns a custom type; the JSO includes a source-generated context for it
        var jso = SkillTestJsonContext.Default.Options;
        var resource = new AgentInlineSkillResource("config", () => new SkillConfig { Theme = "dark", Verbose = true }, serializerOptions: jso);

        // Act
        var result = await resource.ReadAsync();

        // Assert — the custom type was returned successfully
        Assert.NotNull(result);
        Assert.Contains("dark", result!.ToString()!);
    }

    [Fact]
    public async Task ReadAsync_SupportsCancellationTokenAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        var resource = new AgentInlineSkillResource("cancellable", "value");

        // Act — should not throw with a non-cancelled token
        var result = await resource.ReadAsync(cancellationToken: cts.Token);

        // Assert
        Assert.Equal("value", result);
    }
}
