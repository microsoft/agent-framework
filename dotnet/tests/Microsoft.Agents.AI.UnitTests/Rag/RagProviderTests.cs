﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Rag;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Rag;

/// <summary>
/// Contains unit tests for <see cref="RagProvider"/>.
/// </summary>
public sealed class RagProviderTests
{
    private readonly Mock<ILogger<RagProvider>> _loggerMock;
    private readonly Mock<ILoggerFactory> _loggerFactoryMock;

    public RagProviderTests()
    {
        this._loggerMock = new();
        this._loggerFactoryMock = new();
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(It.IsAny<string>()))
            .Returns(this._loggerMock.Object);
        this._loggerFactoryMock
            .Setup(f => f.CreateLogger(typeof(RagProvider).FullName!))
            .Returns(this._loggerMock.Object);
    }

    [Theory]
    [InlineData(null, null, true)]
    [InlineData("Custom context prompt", "Custom citations prompt", false)]
    public async Task InvokingAsync_ShouldInjectFormattedResultsAsync(string? overrideContextPrompt, string? overrideCitationsPrompt, bool withLogging)
    {
        // Arrange
        List<RagProvider.RagSearchResult> results =
        [
            new() { Name = "Doc1", Link = "http://example.com/doc1", Value = "Content of Doc1" },
            new() { Name = "Doc2", Link = "http://example.com/doc2", Value = "Content of Doc2" }
        ];

        string? capturedInput = null;
        Task<IEnumerable<RagProvider.RagSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>(results);
        }

        var options = new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            ContextPrompt = overrideContextPrompt,
            IncludeCitationsPrompt = overrideCitationsPrompt
        };
        var provider = new RagProvider(SearchDelegateAsync, options, withLogging ? this._loggerFactoryMock.Object : null);

        var invokingContext = new AIContextProvider.InvokingContext(new[]
        {
            new ChatMessage(ChatRole.User, "Sample user question?"),
            new ChatMessage(ChatRole.User, "Additional part")
        });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("Sample user question?\nAdditional part", capturedInput);
        Assert.Null(aiContext.Instructions); // RagProvider uses a user message for context injection.
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
                    It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("RAGProvider: Retrieved 2 search results.")),
                    It.IsAny<Exception?>(),
                    It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
                Times.AtLeastOnce);
            this._loggerMock.Verify(
                l => l.Log(
                    LogLevel.Trace,
                    It.IsAny<EventId>(),
                    It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("RAGProvider Input:Sample user question?\nAdditional part\nContext Instructions:") || v.ToString()!.Contains("RAGProvider Input:Sample user question?\nAdditional part\nContext Instructions")),
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
        var options = new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.OnDemandFunctionCalling,
            PluginFunctionName = overrideName,
            PluginFunctionDescription = overrideDescription
        };
        var provider = new RagProvider(this.NoResultSearchAsync, options);
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

    [Theory]
    [InlineData(null, null)]
    [InlineData("Custom context prompt", "Custom citations prompt")]
    public async Task SearchAsync_ShouldReturnFormattedResultsAsync(string? overrideContextPrompt, string? overrideCitationsPrompt)
    {
        // Arrange
        List<RagProvider.RagSearchResult> results =
        [
            new() { Name = "Doc1", Link = "http://example.com/doc1", Value = "Content of Doc1" },
            new() { Name = "Doc2", Link = "http://example.com/doc2", Value = "Content of Doc2" }
        ];

        Task<IEnumerable<RagProvider.RagSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>(results);
        }

        var options = new RagProviderOptions
        {
            ContextPrompt = overrideContextPrompt,
            IncludeCitationsPrompt = overrideCitationsPrompt
        };
        var provider = new RagProvider(SearchDelegateAsync, options);

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
        List<RagProvider.RagSearchResult> results =
        [
            new() { Name = "Doc1", Link = "http://example.com/doc1", Value = "Content of Doc1" },
            new() { Name = "Doc2", Link = "http://example.com/doc2", Value = "Content of Doc2" }
        ];

        Task<IEnumerable<RagProvider.RagSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>(results);
        }

        var options = new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            ContextFormatter = r => $"Custom formatted context with {r.Count} results."
        };
        var provider = new RagProvider(SearchDelegateAsync, options);
        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "Q?") });

        // Act
        var aiContext = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(aiContext.Messages);
        Assert.Single(aiContext.Messages!);
        Assert.Equal("Custom formatted context with 2 results.", aiContext.Messages![0].Text);
    }

    [Fact]
    public async Task InvokingAsync_WithNoResults_ShouldReturnEmptyContextAsync()
    {
        // Arrange
        var options = new RagProviderOptions { SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke };
        var provider = new RagProvider(this.NoResultSearchAsync, options);
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
    public async Task InvokingAsync_WithRecentMessageMemory_ShouldIncludeStoredMessagesInSearchInputAsync()
    {
        // Arrange
        var options = new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3
        };
        string? capturedInput = null;
        Task<IEnumerable<RagProvider.RagSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>([]); // No results needed.
        }
        var provider = new RagProvider(SearchDelegateAsync, options);

        // Populate memory with more messages than the limit (A,B,C,D) -> should retain B,C,D
        var initialMessages = new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
        };
        await provider.InvokedAsync(new(initialMessages));

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
        var options = new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 5
        };
        string? capturedInput = null;
        Task<IEnumerable<RagProvider.RagSearchResult>> SearchDelegateAsync(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>([]);
        }
        var provider = new RagProvider(SearchDelegateAsync, options);

        // First memory update (A,B)
        await provider.InvokedAsync(new(new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
        }));

        // Second memory update (C,D,E)
        await provider.InvokedAsync(new(new[]
        {
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
            new ChatMessage(ChatRole.User, "E"),
        }));

        var invokingContext = new AIContextProvider.InvokingContext(new[] { new ChatMessage(ChatRole.User, "F") });

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("A\nB\nC\nD\nE\nF", capturedInput); // All retained (limit 5) + current request message.
    }

    #endregion

    #region Serialization Tests

    [Fact]
    public void Serialize_WithNoRecentMessages_ShouldReturnEmptyState()
    {
        // Arrange
        var options = new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3
        };
        var provider = new RagProvider(this.NoResultSearchAsync, options);

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
        var options = new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3
        };
        var provider = new RagProvider(this.NoResultSearchAsync, options);
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "M1"),
            new ChatMessage(ChatRole.Assistant, "M2"),
            new ChatMessage(ChatRole.User, "M3"),
        };

        // Act
        await provider.InvokedAsync(new(messages)); // Populate recent memory.
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
        var options = new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 4
        };
        var provider = new RagProvider(this.NoResultSearchAsync, options);
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
            new ChatMessage(ChatRole.Assistant, "D"),
        };
        await provider.InvokedAsync(new(messages));

        // Act
        var state = provider.Serialize();
        string? capturedInput = null;
        Task<IEnumerable<RagProvider.RagSearchResult>> SearchDelegate2Async(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>([]);
        }
        var roundTrippedProvider = new RagProvider(SearchDelegate2Async, state, options: new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
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
        var initialProvider = new RagProvider(this.NoResultSearchAsync, new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 5
        });
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "L1"),
            new ChatMessage(ChatRole.Assistant, "L2"),
            new ChatMessage(ChatRole.User, "L3"),
            new ChatMessage(ChatRole.Assistant, "L4"),
            new ChatMessage(ChatRole.User, "L5"),
        };
        await initialProvider.InvokedAsync(new(messages));
        var state = initialProvider.Serialize();

        string? capturedInput = null;
        Task<IEnumerable<RagProvider.RagSearchResult>> SearchDelegate2Async(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>([]);
        }

        // Act
        var restoredProvider = new RagProvider(SearchDelegate2Async, state, options: new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
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
        Task<IEnumerable<RagProvider.RagSearchResult>> SearchDelegate2Async(string input, CancellationToken ct)
        {
            capturedInput = input;
            return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>([]);
        }

        // Act
        var provider = new RagProvider(SearchDelegate2Async, emptyState, options: new RagProviderOptions
        {
            SearchTime = RagProviderOptions.RagBehavior.BeforeAIInvoke,
            RecentMessageMemoryLimit = 3
        });
        var emptyMessages = Array.Empty<ChatMessage>();
        await provider.InvokingAsync(new(emptyMessages), CancellationToken.None);

        // Assert
        Assert.NotNull(capturedInput);
        Assert.Equal(string.Empty, capturedInput); // No recent messages serialized => empty input.
    }

    #endregion

    private Task<IEnumerable<RagProvider.RagSearchResult>> NoResultSearchAsync(string input, CancellationToken ct)
    {
        return Task.FromResult<IEnumerable<RagProvider.RagSearchResult>>([]);
    }
}
