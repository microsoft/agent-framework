// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

public sealed class ResponseCitationTests : ConformanceTestBase
{
    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task Response_PreservesCitationMetadataAsync(bool streaming, bool annotationOnly)
    {
        // Arrange
        var sourceCitation = new CitationAnnotation
        {
            Url = new Uri("https://example.com/source"),
            Title = "Source",
            AnnotatedRegions =
            [
                new TextSpanAnnotatedRegion { StartIndex = 0, EndIndex = 5 },
                new TextSpanAnnotatedRegion { StartIndex = 6, EndIndex = 11 }
            ]
        };
        var distinctCitation = new CitationAnnotation
        {
            Url = new Uri("https://example.com/source"),
            Title = "Another title",
            AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = 0, EndIndex = 5 }]
        };
        var providerFirstRegion = new CitationAnnotation
        {
            RawRepresentation = new UriCitationMessageAnnotation(new Uri("https://example.com/source"), 0, 5, "Source")
        };
        var providerSecondRegion = new CitationAnnotation
        {
            RawRepresentation = new UriCitationMessageAnnotation(new Uri("https://example.com/source"), 6, 11, "Source")
        };
        var providerDistinctCitation = new CitationAnnotation
        {
            RawRepresentation = new UriCitationMessageAnnotation(new Uri("https://example.com/source"), 0, 5, "Another title")
        };
        List<AIAnnotation> annotations =
        [
            sourceCitation,
            distinctCitation,
            new CitationAnnotation { RawRepresentation = new FileCitationMessageAnnotation("file_123", 2, "report.pdf") },
            new CitationAnnotation { RawRepresentation = new FilePathMessageAnnotation("file_456", 3) },
            new CitationAnnotation
            {
                RawRepresentation = new ContainerFileCitationMessageAnnotation("container_1", "file_789", 6, 11, "chart.png")
            }
        ];
        HttpClient client = await this.CreateTestServerAsync("citations", "Answer with citations.", "Hello world",
            _ => annotationOnly
                ?
                [
                    new TextContent("Hello ") { Annotations = [providerFirstRegion, providerSecondRegion] },
                    new TextContent("world") { Annotations = [providerFirstRegion, providerSecondRegion, providerDistinctCitation] },
                    new TextContent(string.Empty) { Annotations = annotations.GetRange(2, annotations.Count - 2) },
                    new TextContent(string.Empty) { Annotations = [annotations[2]] }
                ]
                : [new TextContent("Hello world") { Annotations = annotations }]);

        // Act
        using HttpResponseMessage response = await this.SendResponsesRequestAsync(client, "citations",
            $$"""{"model":"test","input":"test","stream":{{(streaming ? "true" : "false")}}}""");
        string body = await response.Content.ReadAsStringAsync();

        // Assert
        response.EnsureSuccessStatusCode();
        if (!streaming)
        {
            using JsonDocument document = JsonDocument.Parse(body);
            AssertAnnotations(document.RootElement.GetProperty("output")[0].GetProperty("content")[0].GetProperty("annotations"));
            return;
        }

        List<JsonElement> events = [];
        foreach (string line in body.Split('\n').Where(line => line.StartsWith("data: ", StringComparison.Ordinal)))
        {
            using JsonDocument document = JsonDocument.Parse(line.Substring("data: ".Length));
            events.Add(document.RootElement.Clone());
        }
        JsonElement[] annotationEvents = events.Where(e => e.GetProperty("type").GetString() == "response.output_text.annotation.added").ToArray();
        Assert.Equal(6, annotationEvents.Length);
        for (int i = 0; i < annotationEvents.Length; i++)
        {
            Assert.Equal(i, annotationEvents[i].GetProperty("annotation_index").GetInt32());
            Assert.Equal(0, annotationEvents[i].GetProperty("content_index").GetInt32());
        }

        JsonElement partDone = events.Single(e => e.GetProperty("type").GetString() == "response.content_part.done");
        AssertAnnotations(partDone.GetProperty("part").GetProperty("annotations"));
        for (int i = 0; i < annotationEvents.Length; i++)
        {
            Assert.Equal(partDone.GetProperty("item_id").GetString(), annotationEvents[i].GetProperty("item_id").GetString());
            Assert.Equal(partDone.GetProperty("output_index").GetInt32(), annotationEvents[i].GetProperty("output_index").GetInt32());
            Assert.Equal(partDone.GetProperty("part").GetProperty("annotations")[i].GetRawText(),
                annotationEvents[i].GetProperty("annotation").GetRawText());
        }

        JsonElement itemDone = events.Single(e => e.GetProperty("type").GetString() == "response.output_item.done");
        AssertAnnotations(itemDone.GetProperty("item").GetProperty("content")[0].GetProperty("annotations"));
        JsonElement completed = events.Single(e => e.GetProperty("type").GetString() == "response.completed");
        AssertAnnotations(completed.GetProperty("response").GetProperty("output")[0].GetProperty("content")[0].GetProperty("annotations"));
        Assert.Equal("Hello world", partDone.GetProperty("part").GetProperty("text").GetString());
        Assert.Equal(Enumerable.Range(0, events.Count), events.Select(e => e.GetProperty("sequence_number").GetInt32()));
    }

    [Fact]
    public void ToItemContent_UnsupportedAnnotations_AreSkipped()
    {
        // Arrange
        var text = new TextContent("Hello")
        {
            Annotations =
            [
                new AIAnnotation(),
                new CitationAnnotation { Title = "No URL" },
                new CitationAnnotation { Url = new Uri("https://example.com/no-region") },
                new CitationAnnotation
                {
                    Url = new Uri("https://example.com/incomplete-region"),
                    AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = 0 }]
                }
            ]
        };

        // Act
        var output = Assert.IsType<ItemContentOutputText>(ItemContentConverter.ToItemContent(text));

        // Assert
        Assert.Empty(output.Annotations);
    }

    [Fact]
    public void ToItemContent_UrlCitationWithoutTitle_UsesEmptyTitle()
    {
        // Arrange
        var text = new TextContent("Hello")
        {
            Annotations =
            [
                new CitationAnnotation
                {
                    Url = new Uri("https://example.com/source"),
                    AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = 0, EndIndex = 5 }]
                }
            ]
        };

        // Act
        var output = Assert.IsType<ItemContentOutputText>(ItemContentConverter.ToItemContent(text));

        // Assert
        Assert.Equal(string.Empty, Assert.Single(output.Annotations).GetProperty("title").GetString());
    }

    [Fact]
    public void ToItemContent_RawUrlCitation_PreservesOriginalMetadata()
    {
        // Arrange
        var text = new TextContent("Hello")
        {
            Annotations =
            [
                new CitationAnnotation
                {
                    RawRepresentation = new UriCitationMessageAnnotation(new Uri("https://example.com/raw"), 1, 4, "Original")
                }
            ]
        };

        // Act
        var output = Assert.IsType<ItemContentOutputText>(ItemContentConverter.ToItemContent(text));

        // Assert
        JsonElement annotation = Assert.Single(output.Annotations);
        Assert.Equal("https://example.com/raw", annotation.GetProperty("url").GetString());
        Assert.Equal("Original", annotation.GetProperty("title").GetString());
        Assert.Equal(1, annotation.GetProperty("start_index").GetInt32());
        Assert.Equal(4, annotation.GetProperty("end_index").GetInt32());
    }

    [Fact]
    public void ToItemContent_RawOutputTextWithNewCitation_PreservesRawMetadataWithoutMutation()
    {
        // Arrange
        using JsonDocument existingAnnotation = JsonDocument.Parse("""{"type":"file_path","file_id":"file_1","index":2}""");
        using JsonDocument existingLogprob = JsonDocument.Parse("""{"token":"Hello","logprob":-0.1}""");
        var original = new ItemContentOutputText
        {
            Text = "Hello",
            Annotations = [existingAnnotation.RootElement.Clone()],
            Logprobs = [existingLogprob.RootElement.Clone()]
        };
        var text = Assert.IsType<TextContent>(ItemContentConverter.ToAIContent(original));
        text.Annotations =
        [
            new CitationAnnotation
            {
                Url = new Uri("https://example.com/current"),
                Title = "Current",
                AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = 0, EndIndex = 5 }]
            }
        ];

        // Act
        var output = Assert.IsType<ItemContentOutputText>(ItemContentConverter.ToItemContent(text));

        // Assert
        Assert.NotSame(original, output);
        Assert.Equal("Hello", output.Text);
        Assert.Equal(2, output.Annotations.Count);
        Assert.Equal("file_path", output.Annotations[0].GetProperty("type").GetString());
        Assert.Equal("https://example.com/current", output.Annotations[1].GetProperty("url").GetString());
        Assert.Equal(existingLogprob.RootElement.GetRawText(), Assert.Single(output.Logprobs).GetRawText());
        Assert.Single(original.Annotations);
        Assert.Equal(existingLogprob.RootElement.GetRawText(), Assert.Single(original.Logprobs).GetRawText());
    }

    [Fact]
    public void ToItemContent_StructuredUrlCitationOverridesRawUrlMetadata()
    {
        // Arrange
        var text = new TextContent("Hello world")
        {
            Annotations =
            [
                new CitationAnnotation
                {
                    Url = new Uri("https://example.com/current"),
                    Title = "Current",
                    AnnotatedRegions =
                    [
                        new TextSpanAnnotatedRegion { StartIndex = 0, EndIndex = 5 },
                        new TextSpanAnnotatedRegion { StartIndex = 6, EndIndex = 11 }
                    ],
                    RawRepresentation = new UriCitationMessageAnnotation(new Uri("https://example.com/raw"), 1, 4, "Original")
                }
            ]
        };

        // Act
        var output = Assert.IsType<ItemContentOutputText>(ItemContentConverter.ToItemContent(text));

        // Assert
        Assert.Equal(2, output.Annotations.Count);
        Assert.Equal("https://example.com/current", output.Annotations[0].GetProperty("url").GetString());
        Assert.Equal("Current", output.Annotations[0].GetProperty("title").GetString());
        Assert.Equal(0, output.Annotations[0].GetProperty("start_index").GetInt32());
        Assert.Equal(5, output.Annotations[0].GetProperty("end_index").GetInt32());
        Assert.Equal(6, output.Annotations[1].GetProperty("start_index").GetInt32());
        Assert.Equal(11, output.Annotations[1].GetProperty("end_index").GetInt32());
    }

    [Fact]
    public async Task ToStreamingResponse_AnnotationOnlyUpdateOnCurrentMessage_PreservesCitationAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new()
            {
                MessageId = "message-1",
                Role = ChatRole.Assistant,
                Contents = [new TextContent("Hello")]
            },
            new()
            {
                MessageId = "message-1",
                Role = ChatRole.Assistant,
                Contents = [new AIContent { Annotations = [CreateUrlCitation(0, 5)] }]
            }
        ];

        // Act
        List<StreamingResponseEvent> events = await CollectStreamingEventsAsync(updates);

        // Assert
        StreamingOutputTextAnnotationAdded annotationEvent = Assert.Single(events.OfType<StreamingOutputTextAnnotationAdded>());
        Assert.Equal(0, annotationEvent.AnnotationIndex);
        Assert.Equal("https://example.com/source", annotationEvent.Annotation.GetProperty("url").GetString());
        StreamingOutputItemDone itemDone = Assert.Single(events.OfType<StreamingOutputItemDone>());
        ItemContentOutputText itemContent = Assert.IsType<ItemContentOutputText>(
            Assert.Single(Assert.IsType<ResponsesAssistantMessageItemResource>(itemDone.Item).Content));
        Assert.Equal("Hello", itemContent.Text);
        Assert.Equal(0, Assert.Single(itemContent.Annotations).GetProperty("start_index").GetInt32());
        StreamingContentPartDone partDone = Assert.Single(events.OfType<StreamingContentPartDone>());
        Assert.Equal("https://example.com/source", Assert.Single(Assert.IsType<ItemContentOutputText>(partDone.Part).Annotations)
            .GetProperty("url").GetString());
        StreamingResponseCompleted completed = Assert.Single(events.OfType<StreamingResponseCompleted>());
        ResponsesAssistantMessageItemResource completedItem = Assert.IsType<ResponsesAssistantMessageItemResource>(
            Assert.Single(completed.Response.Output));
        Assert.Equal("https://example.com/source", Assert.Single(Assert.IsType<ItemContentOutputText>(
            Assert.Single(completedItem.Content)).Annotations).GetProperty("url").GetString());
    }

    [Fact]
    public async Task ToStreamingResponse_AnnotationOnlyUpdateOnDifferentMessage_DoesNotAttachToPreviousMessageAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new()
            {
                MessageId = "message-1",
                Role = ChatRole.Assistant,
                Contents = [new TextContent("Hello")]
            },
            new()
            {
                MessageId = "message-2",
                Role = ChatRole.Assistant,
                Contents = [new AIContent { Annotations = [CreateUrlCitation(0, 5)] }]
            }
        ];

        // Act
        List<StreamingResponseEvent> events = await CollectStreamingEventsAsync(updates);

        // Assert
        Assert.Empty(events.OfType<StreamingOutputTextAnnotationAdded>());
        StreamingOutputItemDone itemDone = Assert.Single(events.OfType<StreamingOutputItemDone>());
        ItemContentOutputText itemContent = Assert.IsType<ItemContentOutputText>(
            Assert.Single(Assert.IsType<ResponsesAssistantMessageItemResource>(itemDone.Item).Content));
        Assert.Equal("Hello", itemContent.Text);
        Assert.Empty(itemContent.Annotations);
    }

    [Theory]
    [InlineData("See ", 4)]
    [InlineData("😀", 2)]
    public async Task ToStreamingResponse_SiblingTextContent_RebasesStructuredRegionsButNotProviderOffsetsAsync(string prefix, int textOffset)
    {
        // Arrange
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant,
        [
            new TextContent(prefix),
            new TextContent("Python")
            {
                Annotations =
                [
                    CreateUrlCitation(0, 6),
                    new CitationAnnotation
                    {
                        RawRepresentation = new UriCitationMessageAnnotation(
                            new Uri("https://example.com/provider"), textOffset, textOffset + 6, "Provider")
                    }
                ]
            }
        ]));
        AgentResponseUpdate[] updates = response.ToAgentResponseUpdates();

        // Act
        List<StreamingResponseEvent> events = await CollectStreamingEventsAsync(updates);

        // Assert
        StreamingOutputItemDone itemDone = Assert.Single(events.OfType<StreamingOutputItemDone>());
        ItemContentOutputText itemContent = Assert.IsType<ItemContentOutputText>(
            Assert.Single(Assert.IsType<ResponsesAssistantMessageItemResource>(itemDone.Item).Content));
        Assert.Equal($"{prefix}Python", itemContent.Text);
        Assert.Equal(2, itemContent.Annotations.Count);
        Assert.Equal(textOffset, itemContent.Annotations[0].GetProperty("start_index").GetInt32());
        Assert.Equal(textOffset + 6, itemContent.Annotations[0].GetProperty("end_index").GetInt32());
        Assert.Equal("https://example.com/provider", itemContent.Annotations[1].GetProperty("url").GetString());
        Assert.Equal(textOffset, itemContent.Annotations[1].GetProperty("start_index").GetInt32());
        Assert.Equal(textOffset + 6, itemContent.Annotations[1].GetProperty("end_index").GetInt32());
    }

    private static void AssertAnnotations(JsonElement annotations)
    {
        Assert.Equal(6, annotations.GetArrayLength());
        Assert.Equal("url_citation", annotations[0].GetProperty("type").GetString());
        Assert.Equal("https://example.com/source", annotations[0].GetProperty("url").GetString());
        Assert.Equal("Source", annotations[0].GetProperty("title").GetString());
        Assert.Equal(0, annotations[0].GetProperty("start_index").GetInt32());
        Assert.Equal(5, annotations[0].GetProperty("end_index").GetInt32());
        Assert.Equal(6, annotations[1].GetProperty("start_index").GetInt32());
        Assert.Equal(11, annotations[1].GetProperty("end_index").GetInt32());
        Assert.Equal("Another title", annotations[2].GetProperty("title").GetString());
        Assert.Equal(0, annotations[2].GetProperty("start_index").GetInt32());
        Assert.Equal(5, annotations[2].GetProperty("end_index").GetInt32());
        Assert.Equal("file_citation", annotations[3].GetProperty("type").GetString());
        Assert.Equal("file_123", annotations[3].GetProperty("file_id").GetString());
        Assert.Equal(2, annotations[3].GetProperty("index").GetInt32());
        Assert.Equal("report.pdf", annotations[3].GetProperty("filename").GetString());
        Assert.Equal("file_path", annotations[4].GetProperty("type").GetString());
        Assert.Equal("file_456", annotations[4].GetProperty("file_id").GetString());
        Assert.Equal(3, annotations[4].GetProperty("index").GetInt32());
        Assert.Equal("container_file_citation", annotations[5].GetProperty("type").GetString());
        Assert.Equal("container_1", annotations[5].GetProperty("container_id").GetString());
        Assert.Equal("file_789", annotations[5].GetProperty("file_id").GetString());
        Assert.Equal("chart.png", annotations[5].GetProperty("filename").GetString());
        Assert.Equal(6, annotations[5].GetProperty("start_index").GetInt32());
        Assert.Equal(11, annotations[5].GetProperty("end_index").GetInt32());
    }

    private static CitationAnnotation CreateUrlCitation(int start, int end) =>
        new()
        {
            Url = new Uri("https://example.com/source"),
            Title = "Source",
            AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = start, EndIndex = end }]
        };

    private static async Task<List<StreamingResponseEvent>> CollectStreamingEventsAsync(IEnumerable<AgentResponseUpdate> updates)
    {
        var request = new CreateResponse
        {
            Input = ResponseInput.FromText("test"),
            Model = "test"
        };
        var context = new AgentInvocationContext(new IdGenerator("resp_test", "conv_test"));
        List<StreamingResponseEvent> events = [];
        await foreach (StreamingResponseEvent evt in ToAsyncEnumerableAsync(updates).ToStreamingResponseAsync(request, context))
        {
            events.Add(evt);
        }

        return events;
    }

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(
        IEnumerable<T> values,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (T value in values)
        {
            cancellationToken.ThrowIfCancellationRequested();
            yield return value;
            await Task.Yield();
        }
    }
}
