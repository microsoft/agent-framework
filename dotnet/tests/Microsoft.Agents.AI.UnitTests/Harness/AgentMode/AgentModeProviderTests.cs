// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentModeProvider"/> class.
/// </summary>
public class AgentModeProviderTests
{
    #region ProvideAIContextAsync Tests

    /// <summary>
    /// Verify that the provider returns tools and instructions.
    /// </summary>
    [Fact]
    public async Task ProvideAIContextAsync_ReturnsToolsAndInstructionsAsync()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.NotNull(result.Tools);
        Assert.Equal(2, result.Tools!.Count());
    }

    /// <summary>
    /// Verify that the instructions include the current mode.
    /// </summary>
    [Fact]
    public async Task ProvideAIContextAsync_InstructionsIncludeCurrentModeAsync()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Contains("plan", result.Instructions);
    }

    #endregion

    #region SetMode Tool Tests

    /// <summary>
    /// Verify that SetMode changes the mode.
    /// </summary>
    [Fact]
    public async Task SetMode_ChangesModeAsync()
    {
        // Arrange
        var (tools, state) = await CreateToolsWithStateAsync();
        AIFunction setMode = GetTool(tools, "AgentMode_Set");

        // Act
        await setMode.InvokeAsync(new AIFunctionArguments() { ["mode"] = "execute" });

        // Assert
        Assert.Equal("execute", state.CurrentMode);
    }

    /// <summary>
    /// Verify that SetMode returns a confirmation message.
    /// </summary>
    [Fact]
    public async Task SetMode_ReturnsConfirmationAsync()
    {
        // Arrange
        var (tools, _) = await CreateToolsWithStateAsync();
        AIFunction setMode = GetTool(tools, "AgentMode_Set");

        // Act
        object? result = await setMode.InvokeAsync(new AIFunctionArguments() { ["mode"] = "execute" });

        // Assert
        Assert.Equal("Mode changed to \"execute\".", GetStringResult(result));
    }

    /// <summary>
    /// Verify that SetMode with an unsupported value throws and does not persist the mode.
    /// </summary>
    [Fact]
    public async Task SetMode_InvalidMode_ThrowsAsync()
    {
        // Arrange
        var (tools, provider, session) = await CreateToolsWithProviderAndSessionAsync();
        AIFunction setMode = GetTool(tools, "AgentMode_Set");
        AIFunction getMode = GetTool(tools, "AgentMode_Get");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await setMode.InvokeAsync(new AIFunctionArguments() { ["mode"] = "foo" }));

        // Verify mode was not changed from default
        object? currentMode = await getMode.InvokeAsync(new AIFunctionArguments());
        Assert.Equal("plan", GetStringResult(currentMode));
    }

    #endregion

    #region GetMode Tool Tests

    /// <summary>
    /// Verify that GetMode returns the default mode.
    /// </summary>
    [Fact]
    public async Task GetMode_ReturnsDefaultModeAsync()
    {
        // Arrange
        var (tools, _) = await CreateToolsWithStateAsync();
        AIFunction getMode = GetTool(tools, "AgentMode_Get");

        // Act
        object? result = await getMode.InvokeAsync(new AIFunctionArguments());

        // Assert
        Assert.Equal("plan", GetStringResult(result));
    }

    /// <summary>
    /// Verify that GetMode returns the mode after SetMode.
    /// </summary>
    [Fact]
    public async Task GetMode_ReturnsUpdatedModeAfterSetAsync()
    {
        // Arrange
        var (tools, _) = await CreateToolsWithStateAsync();
        AIFunction setMode = GetTool(tools, "AgentMode_Set");
        AIFunction getMode = GetTool(tools, "AgentMode_Get");

        // Act
        await setMode.InvokeAsync(new AIFunctionArguments() { ["mode"] = "execute" });
        object? result = await getMode.InvokeAsync(new AIFunctionArguments());

        // Assert
        Assert.Equal("execute", GetStringResult(result));
    }

    #endregion

    #region Public Helper Method Tests

    /// <summary>
    /// Verify that the public GetMode helper returns the default mode.
    /// </summary>
    [Fact]
    public void PublicGetMode_ReturnsDefaultMode()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var session = new ChatClientAgentSession();

        // Act
        string mode = provider.GetMode(session);

        // Assert
        Assert.Equal("plan", mode);
    }

    /// <summary>
    /// Verify that the public SetMode helper changes the mode.
    /// </summary>
    [Fact]
    public void PublicSetMode_ChangesMode()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var session = new ChatClientAgentSession();

        // Act
        provider.SetMode(session, "execute");
        string mode = provider.GetMode(session);

        // Assert
        Assert.Equal("execute", mode);
    }

    /// <summary>
    /// Verify that the public SetMode helper throws for an unsupported value and does not persist the mode.
    /// </summary>
    [Fact]
    public void PublicSetMode_InvalidMode_Throws()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var session = new ChatClientAgentSession();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => provider.SetMode(session, "foo"));

        // Verify mode was not changed from default
        string mode = provider.GetMode(session);
        Assert.Equal("plan", mode);
    }

    /// <summary>
    /// Verify that public helper changes are reflected in tool results.
    /// </summary>
    [Fact]
    public async Task PublicSetMode_ReflectedInToolResultsAsync()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();

        // Set mode via public helper
        provider.SetMode(session, "execute");

#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);
        AIFunction getMode = GetTool(result.Tools!, "AgentMode_Get");
        object? modeResult = await getMode.InvokeAsync(new AIFunctionArguments());

        // Assert
        Assert.Equal("execute", GetStringResult(modeResult));
        Assert.Contains("execute", result.Instructions);
    }

    #endregion

    #region State Persistence Tests

    /// <summary>
    /// Verify that state persists across invocations.
    /// </summary>
    [Fact]
    public async Task State_PersistsAcrossInvocationsAsync()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act — first invocation changes mode
        AIContext result1 = await provider.InvokingAsync(context);
        AIFunction setMode = GetTool(result1.Tools!, "AgentMode_Set");
        await setMode.InvokeAsync(new AIFunctionArguments() { ["mode"] = "execute" });

        // Second invocation should see the updated mode
        AIContext result2 = await provider.InvokingAsync(context);
        AIFunction getMode = GetTool(result2.Tools!, "AgentMode_Get");
        object? modeResult = await getMode.InvokeAsync(new AIFunctionArguments());

        // Assert
        Assert.Equal("execute", GetStringResult(modeResult));
        Assert.Contains("execute", result2.Instructions);
    }

    #endregion

    #region Options Tests

    /// <summary>
    /// Verify that custom instructions override the default.
    /// </summary>
    [Fact]
    public async Task Options_CustomInstructions_OverridesDefaultAsync()
    {
        // Arrange
        var options = new AgentModeProviderOptions { Instructions = "Custom mode instructions." };
        var provider = new AgentModeProvider(options);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Equal("Custom mode instructions.", result.Instructions);
    }

    /// <summary>
    /// Verify that custom modes are used.
    /// </summary>
    [Fact]
    public void Options_CustomModes_AreUsed()
    {
        // Arrange
        var options = new AgentModeProviderOptions
        {
            Modes =
            [
                new AgentModeProviderOptions.AgentMode("draft", "Drafting mode."),
                new AgentModeProviderOptions.AgentMode("review", "Review mode."),
            ],
        };
        var provider = new AgentModeProvider(options);
        var session = new ChatClientAgentSession();

        // Act
        string mode = provider.GetMode(session);

        // Assert — default mode is first in list
        Assert.Equal("draft", mode);
    }

    /// <summary>
    /// Verify that SetMode validates against custom modes.
    /// </summary>
    [Fact]
    public void Options_CustomModes_SetModeValidatesAgainstList()
    {
        // Arrange
        var options = new AgentModeProviderOptions
        {
            Modes =
            [
                new AgentModeProviderOptions.AgentMode("draft", "Drafting mode."),
                new AgentModeProviderOptions.AgentMode("review", "Review mode."),
            ],
        };
        var provider = new AgentModeProvider(options);
        var session = new ChatClientAgentSession();

        // Act — valid mode
        provider.SetMode(session, "review");

        // Assert
        Assert.Equal("review", provider.GetMode(session));

        // Act & Assert — invalid mode (plan is no longer valid)
        Assert.Throws<ArgumentException>(() => provider.SetMode(session, "plan"));
    }

    /// <summary>
    /// Verify that a custom default mode is used.
    /// </summary>
    [Fact]
    public void Options_CustomDefaultMode_IsUsed()
    {
        // Arrange
        var options = new AgentModeProviderOptions
        {
            Modes =
            [
                new AgentModeProviderOptions.AgentMode("draft", "Drafting mode."),
                new AgentModeProviderOptions.AgentMode("review", "Review mode."),
            ],
            DefaultMode = "review",
        };
        var provider = new AgentModeProvider(options);
        var session = new ChatClientAgentSession();

        // Act
        string mode = provider.GetMode(session);

        // Assert
        Assert.Equal("review", mode);
    }

    /// <summary>
    /// Verify that an invalid default mode throws.
    /// </summary>
    [Fact]
    public void Options_InvalidDefaultMode_Throws()
    {
        // Arrange
        var options = new AgentModeProviderOptions
        {
            Modes =
            [
                new AgentModeProviderOptions.AgentMode("draft", "Drafting mode."),
            ],
            DefaultMode = "nonexistent",
        };

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentModeProvider(options));
    }

    /// <summary>
    /// Verify that an empty modes list throws.
    /// </summary>
    [Fact]
    public void Options_EmptyModes_Throws()
    {
        // Arrange
        var options = new AgentModeProviderOptions
        {
            Modes = [],
        };

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentModeProvider(options));
    }

    /// <summary>
    /// Verify that custom modes appear in generated instructions.
    /// </summary>
    [Fact]
    public async Task Options_CustomModes_AppearInInstructionsAsync()
    {
        // Arrange
        var options = new AgentModeProviderOptions
        {
            Modes =
            [
                new AgentModeProviderOptions.AgentMode("draft", "Drafting mode description."),
                new AgentModeProviderOptions.AgentMode("review", "Review mode description."),
            ],
        };
        var provider = new AgentModeProvider(options);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Contains("draft", result.Instructions);
        Assert.Contains("Drafting mode description.", result.Instructions);
        Assert.Contains("review", result.Instructions);
        Assert.Contains("Review mode description.", result.Instructions);
    }

    /// <summary>
    /// Verify that AgentMode requires non-empty name and description.
    /// </summary>
    [Fact]
    public void AgentMode_RequiresNameAndDescription()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentModeProviderOptions.AgentMode("", "desc"));
        Assert.Throws<ArgumentException>(() => new AgentModeProviderOptions.AgentMode("name", ""));
        Assert.ThrowsAny<ArgumentException>(() => new AgentModeProviderOptions.AgentMode(null!, "desc"));
        Assert.ThrowsAny<ArgumentException>(() => new AgentModeProviderOptions.AgentMode("name", null!));
    }

    /// <summary>
    /// Verify that duplicate mode names throw.
    /// </summary>
    [Fact]
    public void Options_DuplicateModeNames_Throws()
    {
        // Arrange
        var options = new AgentModeProviderOptions
        {
            Modes =
            [
                new AgentModeProviderOptions.AgentMode("draft", "First draft."),
                new AgentModeProviderOptions.AgentMode("draft", "Second draft."),
            ],
        };

        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new AgentModeProvider(options));
        Assert.Contains("duplicate", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Verify that a null entry in the modes list throws.
    /// </summary>
    [Fact]
    public void Options_NullModeEntry_Throws()
    {
        // Arrange
        var options = new AgentModeProviderOptions
        {
            Modes = new List<AgentModeProviderOptions.AgentMode> { null! },
        };

        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new AgentModeProvider(options));
        Assert.Contains("must not be null", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    #endregion

    #region External Mode Change Notification Tests

    /// <summary>
    /// Verify that an external mode change injects a notification message.
    /// </summary>
    [Fact]
    public async Task ExternalModeChange_InjectsNotificationMessageAsync()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();

        // Change mode externally (simulating /mode command)
        provider.SetMode(session, "execute");

#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Messages);
        Assert.Single(result.Messages!);
        ChatMessage message = result.Messages!.First();
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Contains("plan", message.Text);
        Assert.Contains("execute", message.Text);
    }

    /// <summary>
    /// Verify that the notification is only injected once (cleared after first read).
    /// </summary>
    [Fact]
    public async Task ExternalModeChange_NotificationClearedAfterFirstReadAsync()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
        provider.SetMode(session, "execute");

#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act — first call should have the notification
        AIContext result1 = await provider.InvokingAsync(context);
        Assert.NotNull(result1.Messages);

        // Second call should NOT have the notification
        AIContext result2 = await provider.InvokingAsync(context);

        // Assert
        Assert.Null(result2.Messages);
    }

    /// <summary>
    /// Verify that tool-based mode change does not inject a notification message.
    /// </summary>
    [Fact]
    public async Task ToolModeChange_DoesNotInjectNotificationAsync()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();

#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // First call to initialize
        AIContext result1 = await provider.InvokingAsync(context);
        AIFunction setMode = GetTool(result1.Tools!, "AgentMode_Set");

        // Change mode via the tool (agent-initiated)
        await setMode.InvokeAsync(new AIFunctionArguments() { ["mode"] = "execute" });

        // Act — next call should NOT have a notification
        AIContext result2 = await provider.InvokingAsync(context);

        // Assert
        Assert.Null(result2.Messages);
    }

    /// <summary>
    /// Verify that setting the same mode externally does not inject a notification.
    /// </summary>
    [Fact]
    public async Task ExternalModeChange_SameMode_NoNotificationAsync()
    {
        // Arrange
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();

        // Set to same default mode
        provider.SetMode(session, "plan");

#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Null(result.Messages);
    }

    #endregion

    #region Helper Methods

    private static async Task<(IEnumerable<AITool> Tools, AgentModeState State)> CreateToolsWithStateAsync()
    {
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        AIContext result = await provider.InvokingAsync(context);

        // Retrieve the state from the session to verify mutations
        session.StateBag.TryGetValue<AgentModeState>("AgentModeProvider", out var state, AgentJsonUtilities.DefaultOptions);

        return (result.Tools!, state!);
    }

    private static async Task<(IEnumerable<AITool> Tools, AgentModeProvider Provider, AgentSession Session)> CreateToolsWithProviderAndSessionAsync()
    {
        var provider = new AgentModeProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        AIContext result = await provider.InvokingAsync(context);
        return (result.Tools!, provider, session);
    }

    private static AIFunction GetTool(IEnumerable<AITool> tools, string name)
    {
        return (AIFunction)tools.First(t => t is AIFunction f && f.Name == name);
    }

    private static string GetStringResult(object? result)
    {
        var element = Assert.IsType<JsonElement>(result);
        return element.GetString()!;
    }

    #endregion
}
