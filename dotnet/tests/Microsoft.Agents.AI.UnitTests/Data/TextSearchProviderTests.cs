// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Data;

/// <summary>
/// Contains unit tests for <see cref="TextSearchProvider"/>.
/// </summary>
public sealed class TextSearchProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

    private readonly Mock<ILogger<TextSearchProvider>> _loggerMock;
    private readonly Mock<ILoggerFactory> _loggerFactoryMock;

    public TextSearchProviderTests()
    {
        this._loggerMock = new();
        this._loggerFactoryMock = new();
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(It.IsAny<string>()))
            .Returns(this._loggerMock.Object);
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(typeof(TextSearchProvider).FullName!))
            .Returns(this._loggerMock.Object);

        this._loggerMock
            .Setup(f => f.IsEnabled(It.IsAny<LogLevel>()))
            .Returns(true);
    }

    [Fact]
    public void StateKey_ReturnsDefaultKey_WhenNoOptionsProvided()
    {
        // Arrange & Act
        var provider = new TextSearchProvider((_, _) => Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]));

        // Assert
        Assert.Equal("TextSearchProvider", provider.StateKey);
    }

    [Fact]
    public void StateKey_ReturnsCustomKey_WhenSetViaOptions()
    {
        // Arrange & Act
        var provider = new TextSearchProvider(
            (_, _) => Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]),
            new TextSearchProviderOptions { StateKey = "custom-key" });

        // Assert
        Assert.Equal("custom-key", provider.StateKey);
    }

    [Theory]
    [InlineData(null, null, true)]
    [InlineData("Custom context prompt", "Custom citations prompt", false)]
    public async Task InvokingAsync_ShouldInjectFormattedResultsAsync(string? overrideContextPrompt, string? overrideCitationsPrompt, bool withLogging)
    {
        // Arrange
        List<TextSearchProvider.TextSearchResult> results =
        [
            new() { SourceName = "Doc1", SourceLink = "http://example.com/doc1", Text = "Content of Doc1" },
            new() { SourceName = "Doc2", SourceLink = "http://example.com/doc2", Text = "Content of Doc2" }
        ];

        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>(results);
        }

        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            ContextPrompt = overrideContextPrompt,
            CitationsPrompt = overrideCitationsPrompt
        };
        var provider = new TextSearchProvider(SearchDelegateAsync, options, withLogging ? this._loggerFactoryMock.Object : null);

        var invokingContext = new AIContextProvider.InvokingContext(
            s_mockAgent,
            new TestAgentSession(),
            new AIContext
            {
                Messages = new List<ChatMessage>
                {
                    new(ChatRole.User, "Sample user question?"),
                    new(ChatRole.User, "Additional part")
                }
            });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("Sample user question?\nAdditional part", capturedInput);
        Assert.Null(aiContext.Instructions); // TextSearchProvider uses a user message for context injection.
        Assert.NotNull(aiContext.Messages);
        var messages = aiContext.Messages!.ToList();
        Assert.Equal(3, messages.Count); // 2 input messages + 1 search result message
        Assert.Equal("Sample user question?", messages[0].Text);
        Assert.Equal("Additional part", messages[1].Text);
        Assert.Equal(AgentRequestMessageSourceType.External, messages[0].GetAgentRequestMessageSourceType());
        Assert.Equal(AgentRequestMessageSourceType.External, messages[1].GetAgentRequestMessageSourceType());
        var message = messages.Last();
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, message.GetAgentRequestMessageSourceType());
        string text = message.Text!;

        if (overrideContextPrompt is null)
        {
            Assert.Contains("## Additional Context", text);
            Assert.Contains("Consider the following information from source documents when responding to the user:", text);
        }
        else
        {
            Assert.Contains(overrideContextPrompt, text);
        }
        Assert.Contains("SourceDocName: Doc1", text);
        Assert.Contains("SourceDocLink: http://example.com/doc1", text);
        Assert.Contains("Contents: Content of Doc1", text);
        Assert.Contains("SourceDocName: Doc2", text);
        Assert.Contains("SourceDocLink: http://example.com/doc2", text);
        Assert.Contains("Contents: Content of Doc2", text);
        if (overrideCitationsPrompt is null)
        {
            Assert.Contains("Include citations to the source document with document name and link if document name and link is available.", text);
        }
        else
        {
            Assert.Contains(overrideCitationsPrompt, text);
        }

        if (withLogging)
        {
            this._loggerMock.Verify(
                l => l.Log(
                    LogLevel.Information,
                    It.IsAny<EventId>(),
                    It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("TextSearchProvider: Retrieved 2 search results.")),
                    It.IsAny<Exception?>(),
                    It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
                Times.AtLeastOnce);
            this._loggerMock.Verify(
                l => l.Log(
                    LogLevel.Trace,
                    It.IsAny<EventId>(),
                    It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("TextSearchProvider: Search Results\nInput:Sample user question?\nAdditional part\nOutput")),
                    It.IsAny<Exception?>(),
                    It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
                Times.AtLeastOnce);
        }
    }

    [Theory]
    [InlineData(null, null, "Search", "Allows searching for additional information to help answer the user question.")]
    [InlineData("CustomSearch", "CustomDescription", "CustomSearch", "CustomDescription")]
    public async Task InvokingAsync_OnDemand_ShouldExposeSearchToolAsync(string? overrideName, string? overrideDescription, string expectedName, string expectedDescription)
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.OnDemandFunctionCalling,
            FunctionToolName = overrideName,
            FunctionToolDescription = overrideDescription
        };
        var provider = new TextSearchProvider(this.NoResultSearchAsync, options);
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Q?") } });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages); // Input messages are preserved.
        var messages = aiContext.Messages!.ToList();
        Assert.Single(messages);
        Assert.Equal("Q?", messages[0].Text);
        Assert.NotNull(aiContext.Tools);
        var tools = aiContext.Tools!.ToList();
        Assert.Single(tools);
        var tool = tools[0];
        Assert.Equal(expectedName, tool.Name);
        Assert.Equal(expectedDescription, tool.Description);
    }

    [Fact]
    public async Task InvokingAsync_ShouldNotThrow_WhenSearchFailsAsync()
    {
        // Arrange
        var provider = new TextSearchProvider(this.FailingSearchAsync, loggerFactory: this._loggerFactoryMock.Object);
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Q?") } });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages); // Input messages are preserved on error.
        var messages = aiContext.Messages!.ToList();
        Assert.Single(messages);
        Assert.Equal("Q?", messages[0].Text);
        Assert.Null(aiContext.Tools);
        this._loggerMock.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("TextSearchProvider: Failed to search for data due to error")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);
    }

    [Theory]
    [InlineData(null, null)]
    [InlineData("Custom context prompt", "Custom citations prompt")]
    public async Task SearchAsync_ShouldReturnFormattedResultsAsync(string? overrideContextPrompt, string? overrideCitationsPrompt)
    {
        // Arrange
        List<TextSearchProvider.TextSearchResult> results =
        [
            new() { SourceName = "Doc1", SourceLink = "http://example.com/doc1", Text = "Content of Doc1" },
            new() { SourceName = "Doc2", SourceLink = "http://example.com/doc2", Text = "Content of Doc2" }
        ];

        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>(results);
        }

        var options = new TextSearchProviderOptions
        {
            ContextPrompt = overrideContextPrompt,
            CitationsPrompt = overrideCitationsPrompt
        };
        var provider = new TextSearchProvider(SearchDelegateAsync, options);

        // Act
        var formatted = await provider.SearchAsync("Sample user question?", CancellationToken.None);

        // Assert
        if (overrideContextPrompt is null)
        {
            Assert.Contains("## Additional Context", formatted);
            Assert.Contains("Consider the following information from source documents when responding to the user:", formatted);
        }
        else
        {
            Assert.Contains(overrideContextPrompt, formatted);
        }

        Assert.Contains("SourceDocName: Doc1", formatted);
        Assert.Contains("SourceDocLink: http://example.com/doc1", formatted);
        Assert.Contains("Contents: Content of Doc1", formatted);
        Assert.Contains("SourceDocName: Doc2", formatted);
        Assert.Contains("SourceDocLink: http://example.com/doc2", formatted);
        Assert.Contains("Contents: Content of Doc2", formatted);
        if (overrideCitationsPrompt is null)
        {
            Assert.Contains("Include citations to the source document with document name and link if document name and link is available.", formatted);
        }
        else
        {
            Assert.Contains(overrideCitationsPrompt, formatted);
        }
    }

    [Fact]
    public async Task InvokingAsync_ShouldUseContextFormatterWhenProvidedAsync()
    {
        // Arrange
        List<TextSearchProvider.TextSearchResult> results =
        [
            new() { SourceName = "Doc1", SourceLink = "http://example.com/doc1", Text = "Content of Doc1" },
            new() { SourceName = "Doc2", SourceLink = "http://example.com/doc2", Text = "Content of Doc2" }
        ];

        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>(results);
        }

        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            ContextFormatter = r => $"Custom formatted context with {r.Count} results."
        };
        var provider = new TextSearchProvider(SearchDelegateAsync, options);
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Q?") } });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages);
        var messages = aiContext.Messages!.ToList();
        Assert.Equal(2, messages.Count); // 1 input message + 1 formatted result message
        Assert.Equal("Q?", messages[0].Text);
        Assert.Equal("Custom formatted context with 2 results.", messages[1].Text);
    }

    [Fact]
    public async Task InvokingAsync_WithRawRepresentations_ContextFormatterCanAccessAsync()
    {
        // Arrange
        var payload1 = new RawPayload { Id = "R1" };
        var payload2 = new RawPayload { Id = "R2" };
        List<TextSearchProvider.TextSearchResult> results =
        [
            new() { SourceName = "Doc1", Text = "Content 1", RawRepresentation = payload1 },
            new() { SourceName = "Doc2", Text = "Content 2", RawRepresentation = payload2 }
        ];

        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>(results);
        }

        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            ContextFormatter = r => string.Join(",", r.Select(x => ((RawPayload)x.RawRepresentation!).Id))
        };
        var provider = new TextSearchProvider(SearchDelegateAsync, options);
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Q?") } });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages);
        var messages = aiContext.Messages!.ToList();
        Assert.Equal(2, messages.Count); // 1 input message + 1 formatted result message
        Assert.Equal("Q?", messages[0].Text);
        Assert.Equal("R1,R2", messages[1].Text);
    }

    [Fact]
    public async Task InvokingAsync_WithNoResults_ShouldReturnEmptyContextAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions { SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke };
        var provider = new TextSearchProvider(this.NoResultSearchAsync, options);
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Q?") } });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages); // Input messages are preserved when no results found.
        var messages = aiContext.Messages!.ToList();
        Assert.Single(messages);
        Assert.Equal("Q?", messages[0].Text);
        Assert.Null(aiContext.Instructions);
        Assert.Null(aiContext.Tools);
    }

    #region Message Filter Tests

    [Fact]
    public async Task InvokingAsync_DefaultFilter_ExcludesNonExternalMessagesFromSearchInputAsync()
    {
        // Arrange
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }

        var provider = new TextSearchProvider(SearchDelegateAsync);
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
            new(ChatRole.System, "From context provider") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "ContextSource") } } },
        };

        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = requestMessages });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert - Only external messages should be used for search input
        Assert.Equal("External message", capturedInput);
    }

    [Fact]
    public async Task InvokingAsync_CustomSearchInputFilter_OverridesDefaultAsync()
    {
        // Arrange
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }

        var provider = new TextSearchProvider(SearchDelegateAsync, new TextSearchProviderOptions
        {
            SearchInputMessageFilter = messages => messages.Where(m => m.Role == ChatRole.System)
        });
        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "User message"),
            new(ChatRole.System, "System message"),
        };

        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), new AIContext { Messages = requestMessages });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert - Custom filter keeps only System messages
        Assert.Equal("System message", capturedInput);
    }

    [Fact]
    public async Task InvokedAsync_DefaultFilter_ExcludesNonExternalMessagesFromStorageAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            RecentMessageMemoryLimit = 10,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.System]
        };
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }
        var provider = new TextSearchProvider(SearchDelegateAsync, options);
        var session = new TestAgentSession();

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
            new(ChatRole.System, "From context provider") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "ContextSource") } } },
        };

        // Store messages via InvokedAsync
        await provider.InvokedAsync(new(s_mockAgent, session, requestMessages, []));

        // Now invoke to read stored memory
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, session, new AIContext { Messages = [new ChatMessage(ChatRole.User, "Next")] });
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert - Only "External message" was stored in memory, so search input = "External message" + "Next"
        Assert.Equal("External message\nNext", capturedInput);
    }

    [Fact]
    public async Task InvokedAsync_CustomStorageInputFilter_OverridesDefaultAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            RecentMessageMemoryLimit = 10,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.System],
            StorageInputMessageFilter = messages => messages // No filtering - store everything
        };
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }
        var provider = new TextSearchProvider(SearchDelegateAsync, options);
        var session = new TestAgentSession();

        var requestMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "External message"),
            new(ChatRole.System, "From history") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistorySource") } } },
        };

        // Store messages via InvokedAsync
        await provider.InvokedAsync(new(s_mockAgent, session, requestMessages, []));

        // Now invoke to read stored memory
        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, session, new AIContext { Messages = [new ChatMessage(ChatRole.User, "Next")] });
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert - Both messages stored (identity filter), so search input includes all + current
        Assert.Equal("External message\nFrom history\nNext", capturedInput);
    }

    #endregion

    #region Recent Message Memory Tests

    [Fact]
    public async Task InvokingAsync_WithPreviousFailedRequest_ShouldNotIncludeFailedRequestInputInSearchInputAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3
        };
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]); // No results needed.
        }
        var provider = new TextSearchProvider(SearchDelegateAsync, options);

        // Populate memory with more messages than the limit (A,B,C,D) -> should retain B,C,D
        var initialMessages = new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
        };

        var session = new TestAgentSession();
        await provider.InvokedAsync(new(s_mockAgent, session, initialMessages, new InvalidOperationException("Request Failed")));

        var invokingContext = new AIContextProvider.InvokingContext(
            s_mockAgent,
            session,
            new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "E") } });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("E", capturedInput); // Only the messages from the current request, since previous failed request should not be stored.
    }

    [Fact]
    public async Task InvokingAsync_WithRecentMessageMemory_ShouldIncludeStoredMessagesInSearchInputAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.Assistant]
        };
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]); // No results needed.
        }
        var provider = new TextSearchProvider(SearchDelegateAsync, options);
        var session = new TestAgentSession();

        // Populate memory with more messages than the limit (A,B,C,D) -> should retain B,C,D
        var initialMessages = new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
        };
        await provider.InvokedAsync(new(s_mockAgent, session, initialMessages, []));

        var invokingContext = new AIContextProvider.InvokingContext(
            s_mockAgent,
            session,
            new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "E") } });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("B\nC\nD\nE", capturedInput); // Memory first (truncated) then current request.
    }

    [Fact]
    public async Task InvokingAsync_WithAccumulatedMemoryAcrossInvocations_ShouldIncludeAllUpToLimitAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 5,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.Assistant]
        };
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }
        var provider = new TextSearchProvider(SearchDelegateAsync, options);
        var session = new TestAgentSession();

        // First memory update (A,B)
        await provider.InvokedAsync(new(
            s_mockAgent,
            session,
            [
                new ChatMessage(ChatRole.User, "A"),
                new ChatMessage(ChatRole.Assistant, "B"),
            ],
            []));

        // Second memory update (C,D,E)
        await provider.InvokedAsync(new(
            s_mockAgent,
            session,
            [
                new ChatMessage(ChatRole.User, "C"),
                new ChatMessage(ChatRole.Assistant, "D"),
                new ChatMessage(ChatRole.User, "E"),
            ],
            []));

        var invokingContext = new AIContextProvider.InvokingContext(s_mockAgent, session, new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "F") } });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("A\nB\nC\nD\nE\nF", capturedInput); // All retained (limit 5) + current request message.
    }

    [Fact]
    public async Task InvokingAsync_WithRecentMessageRolesIncluded_ShouldFilterRolesAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 4,
            RecentMessageRolesIncluded = [ChatRole.Assistant] // Only retain assistant messages.
        };
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]); // No results needed for this test.
        }
        var provider = new TextSearchProvider(SearchDelegateAsync, options);
        var session = new TestAgentSession();

        // Populate memory with mixed roles; only Assistant messages (A1,A2) should be retained.
        var initialMessages = new[]
        {
            new ChatMessage(ChatRole.User, "U1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "U2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        };
        await provider.InvokedAsync(new(s_mockAgent, session, initialMessages, []));

        var invokingContext = new AIContextProvider.InvokingContext(
            s_mockAgent,
            session,
            new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "Question?") } }); // Current request message always appended.

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("A1\nA2\nQuestion?", capturedInput); // Only assistant messages from memory + current request.
    }

    #endregion

    #region Serialization Tests

    [Fact]
    public async Task InvokedAsync_ShouldPersistMessagesToSessionStateBagAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.Assistant]
        };
        var provider = new TextSearchProvider(this.NoResultSearchAsync, options);
        var session = new TestAgentSession();
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "M1"),
            new ChatMessage(ChatRole.Assistant, "M2"),
            new ChatMessage(ChatRole.User, "M3"),
        };

        // Act
        await provider.InvokedAsync(new(s_mockAgent, session, messages, [])); // Populate recent memory.

        // Assert - State should be in the session's StateBag
        var stateBagSerialized = session.StateBag.Serialize();
        Assert.True(stateBagSerialized.TryGetProperty("TextSearchProvider", out var stateProperty));
        Assert.True(stateProperty.TryGetProperty("recentMessagesText", out var recentProperty));
        Assert.Equal(JsonValueKind.Array, recentProperty.ValueKind);
        var list = recentProperty.EnumerateArray().Select(e => e.GetString()).ToList();
        Assert.Equal(3, list.Count);
        Assert.Equal(["M1", "M2", "M3"], list);
    }

    [Fact]
    public async Task StateBag_RoundtripRestoresMessagesAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 4,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.Assistant]
        };
        var provider = new TextSearchProvider(this.NoResultSearchAsync, options);
        var session = new TestAgentSession();
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
        };
        await provider.InvokedAsync(new(s_mockAgent, session, messages, []));

        // Act - Serialize and deserialize the StateBag
        var serializedStateBag = session.StateBag.Serialize();
        var restoredSession = new TestAgentSession(AgentSessionStateBag.Deserialize(serializedStateBag));

        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegate2Async(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }
        var newProvider = new TextSearchProvider(SearchDelegate2Async, new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 4
        });
        await newProvider.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, restoredSession, new AIContext()), CancellationToken.None); // Trigger search to read memory.

        // Assert
        Assert.NotNull(capturedInput);
        Assert.Equal("A\nB\nC\nD", capturedInput);
    }

    [Fact]
    public async Task InvokingAsync_WithEmptyStateBag_ShouldHaveNoMessagesAsync()
    {
        // Arrange
        var session = new TestAgentSession(); // Fresh session with empty StateBag

        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegate2Async(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }

        // Act
        var provider = new TextSearchProvider(SearchDelegate2Async, new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3
        });
        await provider.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, session, new AIContext()), CancellationToken.None);

        // Assert
        Assert.NotNull(capturedInput);
        Assert.Equal(string.Empty, capturedInput); // No recent messages in StateBag => empty input.
    }

    #endregion

    #region MessageAIContextProvider.InvokingAsync Tests

    [Fact]
    public async Task MessageInvokingAsync_BeforeAIInvoke_SearchesAndReturnsMergedMessagesAsync()
    {
        // Arrange
        List<TextSearchProvider.TextSearchResult> results =
        [
            new() { SourceName = "Doc1", Text = "Content of Doc1" }
        ];

        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
            => Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>(results);

        var provider = new TextSearchProvider(SearchDelegateAsync, new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke
        });

        var inputMsg = new ChatMessage(ChatRole.User, "Question?");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), [inputMsg]);

        // Act
        var messages = (await provider.InvokingAsync(context)).ToList();

        // Assert - input message + search result message, with stamping
        Assert.Equal(2, messages.Count);
        Assert.Equal("Question?", messages[0].Text);
        Assert.Contains("Content of Doc1", messages[1].Text);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, messages[1].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public async Task MessageInvokingAsync_OnDemand_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var provider = new TextSearchProvider(this.NoResultSearchAsync, new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.OnDemandFunctionCalling,
        });
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), [new ChatMessage(ChatRole.User, "Q?")]);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => provider.InvokingAsync(context).AsTask());
    }

    [Fact]
    public async Task MessageInvokingAsync_BeforeAIInvoke_NoResults_ReturnsOnlyInputMessagesAsync()
    {
        // Arrange
        var provider = new TextSearchProvider(this.NoResultSearchAsync, new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke
        });
        var inputMsg = new ChatMessage(ChatRole.User, "Hello");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), [inputMsg]);

        // Act
        var messages = (await provider.InvokingAsync(context)).ToList();

        // Assert
        Assert.Single(messages);
        Assert.Equal("Hello", messages[0].Text);
    }

    [Fact]
    public async Task MessageInvokingAsync_BeforeAIInvoke_DefaultFilter_ExcludesNonExternalMessagesAsync()
    {
        // Arrange
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }

        var provider = new TextSearchProvider(SearchDelegateAsync, new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke
        });

        var externalMsg = new ChatMessage(ChatRole.User, "External message");
        var historyMsg = new ChatMessage(ChatRole.System, "From history")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, new TestAgentSession(), [externalMsg, historyMsg]);

        // Act
        await provider.InvokingAsync(context);

        // Assert - Only External message used for search query
        Assert.Equal("External message", capturedInput);
    }

    #endregion

    private Task<IEnumerable<TextSearchProvider.TextSearchResult>> NoResultSearchAsync(string input, CancellationToken ct)
    {
        return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
    }

    private Task<IEnumerable<TextSearchProvider.TextSearchResult>> FailingSearchAsync(string input, CancellationToken ct)
    {
        throw new InvalidOperationException("Search Failed");
    }

    private sealed class RawPayload
    {
        public string Id { get; set; } = string.Empty;
    }

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
        }

        public TestAgentSession(AgentSessionStateBag stateBag)
        {
            this.StateBag = stateBag;
        }
    }
}
