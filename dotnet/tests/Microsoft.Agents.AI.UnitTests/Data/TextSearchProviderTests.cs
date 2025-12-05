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
        var provider = new TextSearchProvider(SearchDelegateAsync, default, null, options, withLogging ? this._loggerFactoryMock.Object : null);

        var invokingContext = new AIContextProvider.InvokingContext(
        [
            new ChatMessage(ChatRole.User, "Sample user question?"),
            new ChatMessage(ChatRole.User, "Additional part")
        ]);

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("Sample user question?\nAdditional part", capturedInput);
        Assert.Null(aiContext.Instructions); // TextSearchProvider uses a user message for context injection.
        Assert.NotNull(aiContext.Messages);
        Assert.Single(aiContext.Messages!);
        var message = aiContext.Messages!.Single();
        Assert.Equal(ChatRole.User, message.Role);
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
        var provider = new TextSearchProvider(this.NoResultSearchAsync, default, null, options);
        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "Q?") });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Null(aiContext.Messages); // No automatic injection.
        Assert.NotNull(aiContext.Tools);
        Assert.Single(aiContext.Tools);
        var tool = aiContext.Tools.Single();
        Assert.Equal(expectedName, tool.Name);
        Assert.Equal(expectedDescription, tool.Description);
    }

    [Fact]
    public async Task InvokingAsync_ShouldNotThrow_WhenSearchFailsAsync()
    {
        // Arrange
        var provider = new TextSearchProvider(this.FailingSearchAsync, default, null, loggerFactory: this._loggerFactoryMock.Object);
        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "Q?") });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Null(aiContext.Messages);
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
        var provider = new TextSearchProvider(SearchDelegateAsync, default, null, options);

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
        var provider = new TextSearchProvider(SearchDelegateAsync, default, null, options);
        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "Q?") });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages);
        Assert.Single(aiContext.Messages!);
        Assert.Equal("Custom formatted context with 2 results.", aiContext.Messages![0].Text);
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
        var provider = new TextSearchProvider(SearchDelegateAsync, default, null, options);
        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "Q?") });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages);
        Assert.Single(aiContext.Messages!);
        Assert.Equal("R1,R2", aiContext.Messages![0].Text);
    }

    [Fact]
    public async Task InvokingAsync_WithNoResults_ShouldReturnEmptyContextAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions { SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke };
        var provider = new TextSearchProvider(this.NoResultSearchAsync, default, null, options);
        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "Q?") });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Null(aiContext.Messages);
        Assert.Null(aiContext.Instructions);
        Assert.Null(aiContext.Tools);
    }

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
        var provider = new TextSearchProvider(SearchDelegateAsync, default, null, options);

        // Populate memory with more messages than the limit (A,B,C,D) -> should retain B,C,D
        var initialMessages = new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
        };
        await provider.InvokedAsync(new(initialMessages, aiContextProviderMessages: null) { InvokeException = new InvalidOperationException("Request Failed") });

        var invokingContext = new AIContextProvider.InvokingContext(new[]
        {
            new ChatMessage(ChatRole.User, "E")
        });

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
        var provider = new TextSearchProvider(SearchDelegateAsync, default, null, options);

        // Populate memory with more messages than the limit (A,B,C,D) -> should retain B,C,D
        var initialMessages = new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
        };
        await provider.InvokedAsync(new(initialMessages, aiContextProviderMessages: null));

        var invokingContext = new AIContextProvider.InvokingContext(new[]
        {
            new ChatMessage(ChatRole.User, "E")
        });

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
        var provider = new TextSearchProvider(SearchDelegateAsync, default, null, options);

        // First memory update (A,B)
        await provider.InvokedAsync(new(new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
        }, aiContextProviderMessages: null));

        // Second memory update (C,D,E)
        await provider.InvokedAsync(new(new[]
        {
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
            new ChatMessage(ChatRole.User, "E"),
        }, aiContextProviderMessages: null));

        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "F") });

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
        var provider = new TextSearchProvider(SearchDelegateAsync, default, null, options);

        // Populate memory with mixed roles; only Assistant messages (A1,A2) should be retained.
        var initialMessages = new[]
        {
            new ChatMessage(ChatRole.User, "U1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "U2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
        };
        await provider.InvokedAsync(new(initialMessages, null));

        var invokingContext = new AIContextProvider.InvokingContext(new[]
        {
            new ChatMessage(ChatRole.User, "Question?") // Current request message always appended.
        });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("A1\nA2\nQuestion?", capturedInput); // Only assistant messages from memory + current request.
    }

    #endregion

    #region Serialization Tests

    [Fact]
    public void Serialize_WithNoRecentMessages_ShouldReturnEmptyState()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3
        };
        var provider = new TextSearchProvider(this.NoResultSearchAsync, default, null, options);

        // Act
        var state = provider.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, state.ValueKind);
        Assert.False(state.TryGetProperty("recentMessagesText", out _));
    }

    [Fact]
    public async Task Serialize_WithRecentMessages_ShouldPersistMessagesUpToLimitAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.Assistant]
        };
        var provider = new TextSearchProvider(this.NoResultSearchAsync, default, null, options);
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "M1"),
            new ChatMessage(ChatRole.Assistant, "M2"),
            new ChatMessage(ChatRole.User, "M3"),
        };

        // Act
        await provider.InvokedAsync(new(messages, aiContextProviderMessages: null)); // Populate recent memory.
        var state = provider.Serialize();

        // Assert
        Assert.True(state.TryGetProperty("recentMessagesText", out var recentProperty));
        Assert.Equal(JsonValueKind.Array, recentProperty.ValueKind);
        var list = recentProperty.EnumerateArray().Select(e => e.GetString()).ToList();
        Assert.Equal(3, list.Count);
        Assert.Equal(["M1", "M2", "M3"], list);
    }

    [Fact]
    public async Task SerializeAndDeserialize_RoundtripRestoresMessagesAsync()
    {
        // Arrange
        var options = new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 4,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.Assistant]
        };
        var provider = new TextSearchProvider(this.NoResultSearchAsync, default, null, options);
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
        };
        await provider.InvokedAsync(new(messages, aiContextProviderMessages: null));

        // Act
        var state = provider.Serialize();
        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegate2Async(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }
        var roundTrippedProvider = new TextSearchProvider(SearchDelegate2Async, state, options: new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 4
        });
        var emptyMessages = Array.Empty<ChatMessage>();
        await roundTrippedProvider.InvokingAsync(new(emptyMessages), CancellationToken.None); // Trigger search to read memory.

        // Assert
        Assert.NotNull(capturedInput);
        Assert.Equal("A\nB\nC\nD", capturedInput);
    }

    [Fact]
    public async Task Deserialize_WithChangedLowerLimit_ShouldTruncateToNewLimitAsync()
    {
        // Arrange
        var initialProvider = new TextSearchProvider(this.NoResultSearchAsync, default, null, new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 5,
            RecentMessageRolesIncluded = [ChatRole.User, ChatRole.Assistant]
        });
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "L1"),
            new ChatMessage(ChatRole.Assistant, "L2"),
            new ChatMessage(ChatRole.User, "L3"),
            new ChatMessage(ChatRole.Assistant, "L4"),
            new ChatMessage(ChatRole.User, "L5"),
        };
        await initialProvider.InvokedAsync(new(messages, aiContextProviderMessages: null));
        var state = initialProvider.Serialize();

        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegate2Async(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }

        // Act
        var restoredProvider = new TextSearchProvider(SearchDelegate2Async, state, options: new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3 // Lower limit
        });
        await restoredProvider.InvokingAsync(new(Array.Empty<ChatMessage>()), CancellationToken.None);

        // Assert
        Assert.NotNull(capturedInput);
        Assert.Equal("L1\nL2\nL3", capturedInput);
    }

    [Fact]
    public async Task Deserialize_WithEmptyState_ShouldHaveNoMessagesAsync()
    {
        // Arrange
        var emptyState = JsonSerializer.Deserialize("{}", TestJsonSerializerContext.Default.JsonElement);

        string? capturedInput = null;
        Task<IEnumerable<TextSearchProvider.TextSearchResult>> SearchDelegate2Async(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<TextSearchProvider.TextSearchResult>>([]);
        }

        // Act
        var provider = new TextSearchProvider(SearchDelegate2Async, emptyState, options: new TextSearchProviderOptions
        {
            SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3
        });
        var emptyMessages = Array.Empty<ChatMessage>();
        await provider.InvokingAsync(new(emptyMessages), CancellationToken.None);

        // Assert
        Assert.NotNull(capturedInput);
        Assert.Equal(string.Empty, capturedInput); // No recent messages serialized => empty input.
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
}
