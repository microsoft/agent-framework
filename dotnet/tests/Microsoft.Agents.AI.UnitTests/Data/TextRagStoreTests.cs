// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Data;
using Microsoft.Extensions.VectorData;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Data;

/// <summary>
/// Contains unit tests for the <see cref="TextRagStore{TKey}"/> class.
/// </summary>
public class TextRagStoreTests
{
    private readonly Mock<VectorStore> _vectorStoreMock;
    private readonly Mock<VectorStoreCollection<string, TextRagStore<string>.TextRagStorageDocument<string>>> _recordCollectionMock;
    private readonly Mock<IKeywordHybridSearchable<TextRagStore<string>.TextRagStorageDocument<string>>> _keywordHybridSearchableMock;

    public TextRagStoreTests()
    {
        // Arrange common mocks
        this._vectorStoreMock = new Mock<VectorStore>();
        this._recordCollectionMock = new Mock<VectorStoreCollection<string, TextRagStore<string>.TextRagStorageDocument<string>>>();
        this._keywordHybridSearchableMock = new Mock<IKeywordHybridSearchable<TextRagStore<string>.TextRagStorageDocument<string>>>();

        this._vectorStoreMock
            .Setup(v => v.GetCollection<string, TextRagStore<string>.TextRagStorageDocument<string>>("testCollection", It.IsAny<VectorStoreCollectionDefinition>()))
            .Returns(this._recordCollectionMock.Object);
    }

    #region Upsert Validation Tests

    [Fact]
    public async Task UpsertDocumentsAsync_Throws_WhenDocumentsNullAsync()
    {
        // Arrange
        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => store.UpsertDocumentsAsync(null!));
    }

    [Fact]
    public async Task UpsertTextAsync_Throws_WhenTextChunksNullAsync()
    {
        // Arrange
        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => store.UpsertTextAsync(null!));
    }

    [Theory]
    [InlineData(null)]
    [InlineData(" ")]
    public async Task UpsertDocumentsAsync_Throws_WhenDocumentTextNullOrWhitespaceAsync(string? text)
    {
        // Arrange
        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);
        this._recordCollectionMock
            .Setup(r => r.UpsertAsync(It.IsAny<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(), It.IsAny<CancellationToken>()))
            .Callback((IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>> docs, CancellationToken ct) => _ = docs.ToList())
            .Returns(Task.CompletedTask);

        var documents = new List<TextRagDocument> { new() { Text = text } };

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => store.UpsertDocumentsAsync(documents));
    }

    [Theory]
    [InlineData(null)]
    [InlineData(" ")]
    public async Task UpsertTextAsync_Throws_WhenTextChunkNullOrWhitespaceAsync(string? text)
    {
        // Arrange
        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);
        this._recordCollectionMock
            .Setup(r => r.UpsertAsync(It.IsAny<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(), It.IsAny<CancellationToken>()))
            .Callback((IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>> docs, CancellationToken ct) => _ = docs.ToList())
            .Returns(Task.CompletedTask);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => store.UpsertTextAsync([text!]));
    }

    #endregion

    #region Upsert Success Tests

    [Fact]
    public async Task UpsertDocumentsAsync_CreatesCollection_And_UpsertsDocumentAsync()
    {
        // Arrange
        this._recordCollectionMock
            .Setup(r => r.UpsertAsync(It.IsAny<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);

        var documents = new List<TextRagDocument>
        {
            new() { Text = "Sample text", Namespaces = ["ns1"], SourceId = "sid", SourceLink = "sl", SourceName = "sn" }
        };

        // Act
        await store.UpsertDocumentsAsync(documents);

        // Assert
        this._recordCollectionMock.Verify(r => r.EnsureCollectionExistsAsync(It.IsAny<CancellationToken>()), Times.Once);
        this._recordCollectionMock.Verify(r => r.UpsertAsync(
            It.Is<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(doc =>
                doc.Count() == 1 &&
                doc.First().Text == "Sample text" &&
                doc.First().Namespaces.Count == 1 &&
                doc.First().Namespaces[0] == "ns1" &&
                doc.First().SourceId == "sid" &&
                doc.First().SourceLink == "sl" &&
                doc.First().SourceName == "sn" &&
                doc.First().TextEmbedding == "Sample text"),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task UpsertDocumentsAsync_UsesSourceId_AsPrimaryKey_WhenConfiguredAsync()
    {
        // Arrange
        this._recordCollectionMock
            .Setup(r => r.UpsertAsync(It.IsAny<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128, new() { UseSourceIdAsPrimaryKey = true });

        var documents = new List<TextRagDocument>
        {
            new() { Text = "Sample text", Namespaces = ["ns1"], SourceId = "sid", SourceLink = "sl", SourceName = "sn" }
        };

        // Act
        await store.UpsertDocumentsAsync(documents);

        // Assert
        this._recordCollectionMock.Verify(r => r.UpsertAsync(
            It.Is<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(doc => doc.Single().Key == "sid"),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task UpsertDocumentsAsync_DoesNotPersistSourceText_WhenConfiguredAsync()
    {
        // Arrange
        this._recordCollectionMock
            .Setup(r => r.UpsertAsync(It.IsAny<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);

        var documents = new List<TextRagDocument>
        {
            new() { Text = "Sample text", Namespaces = ["ns1"], SourceId = "sid", SourceLink = "sl", SourceName = "sn" }
        };

        // Act
        await store.UpsertDocumentsAsync(documents, new() { DoNotPersistSourceText = true });

        // Assert
        this._recordCollectionMock.Verify(r => r.UpsertAsync(
            It.Is<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(doc =>
                doc.Count() == 1 && doc.First().Text == null && doc.First().TextEmbedding == "Sample text"),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task UpsertTextAsync_CreatesCollection_And_UpsertsDocumentAsync()
    {
        // Arrange
        this._recordCollectionMock
            .Setup(r => r.UpsertAsync(It.IsAny<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);

        // Act
        await store.UpsertTextAsync(["Sample text"]);

        // Assert
        this._recordCollectionMock.Verify(r => r.EnsureCollectionExistsAsync(It.IsAny<CancellationToken>()), Times.Once);
        this._recordCollectionMock.Verify(r => r.UpsertAsync(
            It.Is<IEnumerable<TextRagStore<string>.TextRagStorageDocument<string>>>(doc =>
                doc.Count() == 1 &&
                doc.First().Text == "Sample text" &&
                doc.First().Namespaces.Count == 0 &&
                doc.First().SourceId == null &&
                doc.First().SourceLink == null &&
                doc.First().SourceName == null &&
                doc.First().TextEmbedding == "Sample text"),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    #endregion

    #region Search Tests

    [Fact]
    public async Task SearchAsync_ReturnsSearchResultsAsync()
    {
        // Arrange
        var mockResults = new List<VectorSearchResult<TextRagStore<string>.TextRagStorageDocument<string>>>
        {
            new(new TextRagStore<string>.TextRagStorageDocument<string> { Text = "Sample text" }, 0.9f)
        };

        this._recordCollectionMock
            .Setup(r => r.SearchAsync("query", 3, It.IsAny<VectorSearchOptions<TextRagStore<string>.TextRagStorageDocument<string>>>(), It.IsAny<CancellationToken>()))
            .Returns(mockResults.ToAsyncEnumerable());

        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);

        // Act
        var results = await store.SearchAsync("query", 3);

        // Assert
        var list = results.ToList();
        Assert.Single(list);
        Assert.Equal("Sample text", list[0].Text);
    }

    [Fact]
    public async Task SearchAsync_WithHybrid_ReturnsSearchResultsAsync()
    {
        // Arrange
        this._recordCollectionMock
            .Setup(r => r.GetService(typeof(IKeywordHybridSearchable<TextRagStore<string>.TextRagStorageDocument<string>>), null))
            .Returns(this._keywordHybridSearchableMock.Object);

        var mockResults = new List<VectorSearchResult<TextRagStore<string>.TextRagStorageDocument<string>>>
        {
            new(new TextRagStore<string>.TextRagStorageDocument<string> { Text = "Sample text" }, 0.9f)
        };

        this._keywordHybridSearchableMock
            .Setup(h => h.HybridSearchAsync(
                "query one two",
                It.Is<ICollection<string>>(c => c.Contains("query") && c.Contains("one") && c.Contains("two")),
                3,
                It.IsAny<HybridSearchOptions<TextRagStore<string>.TextRagStorageDocument<string>>>(),
                It.IsAny<CancellationToken>()))
            .Returns(mockResults.ToAsyncEnumerable());

        using var store = new TextRagStore<string>(this._vectorStoreMock.Object, "testCollection", 128);

        // Act
        var results = await store.SearchAsync("query one two", 3);

        // Assert
        var list = results.ToList();
        Assert.Single(list);
        Assert.Equal("Sample text", list[0].Text);
    }

    [Fact]
    public async Task SearchAsync_WithHydration_InvokesCallbackAndHydratesResultsAsync()
    {
        // Arrange
        var mockResults = new List<VectorSearchResult<TextRagStore<string>.TextRagStorageDocument<string>>>
        {
            new(new TextRagStore<string>.TextRagStorageDocument<string> { SourceId = "sid1", SourceLink = "sl1", Text = "Sample text 1" }, 0.9f),
            new(new TextRagStore<string>.TextRagStorageDocument<string> { SourceId = "sid2", SourceLink = "sl2" }, 0.9f),
            new(new TextRagStore<string>.TextRagStorageDocument<string> { SourceId = "sid3", SourceLink = "sl3", Text = "Sample text 3" }, 0.9f)
        };

        this._recordCollectionMock
            .Setup(r => r.SearchAsync("query", 3, It.IsAny<VectorSearchOptions<TextRagStore<string>.TextRagStorageDocument<string>>>(), It.IsAny<CancellationToken>()))
            .Returns(mockResults.ToAsyncEnumerable());

        using var store = new TextRagStore<string>(
            this._vectorStoreMock.Object,
            "testCollection",
            128,
            new()
            {
                SourceRetrievalCallback = requests => Task.FromResult<IEnumerable<TextRagStoreOptions.SourceRetrievalResponse>>([
                    new(new TextRagStoreOptions.SourceRetrievalRequest("sid2", "sl2"), "Sample text 2")
                ])
            });

        // Act
        var results = await store.SearchAsync("query", 3);

        // Assert
        var list = results.ToList();
        Assert.Equal(3, list.Count);
        Assert.Equal("Sample text 1", list[0].Text);
        Assert.Equal("Sample text 2", list[1].Text);
        Assert.Equal("Sample text 3", list[2].Text);
    }

    #endregion
}
