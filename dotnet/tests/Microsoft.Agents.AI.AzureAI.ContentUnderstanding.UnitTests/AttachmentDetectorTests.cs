// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 3 / dev plan task 3.2 — AttachmentDetector walks ChatMessage.Contents and resolves
/// media type + filename for each <see cref="DataContent"/> / <see cref="UriContent"/>.
/// </summary>
public sealed class AttachmentDetectorTests
{
    private static readonly byte[] PdfBytes =
    [
        0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x37, 0x0A, 0x25, 0xE2, 0xE3, 0xCF, 0xD3,
    ];

    private static readonly byte[] PngBytes =
    [
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00,
    ];

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestBeforeRunNewFile::test_text_only_skipped (no attachment)
    public void YieldsEmpty_ForMessagesWithoutSupportedContent()
    {
        ChatMessage msg = new(ChatRole.User, [new TextContent("hello")]);
        Assert.Empty(AttachmentDetector.Detect([msg]));
    }

    [Fact]
    // parity: N/A — .NET-only empty-collection guard.
    public void YieldsEmpty_ForEmptyMessages()
        => Assert.Empty(AttachmentDetector.Detect([]));

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestMimeSniffing::test_correct_mime_not_sniffed (fast-path)
    public void DetectsDataContent_WithExplicitMediaType()
    {
        DataContent dc = new(PdfBytes, "application/pdf") { Name = "contract.pdf" };
        ChatMessage msg = new(ChatRole.User, [new TextContent("Read this"), dc]);

        DetectedAttachment[] detected = AttachmentDetector.Detect([msg]).ToArray();

        Assert.Single(detected);
        Assert.Equal("application/pdf", detected[0].ResolvedMediaType);
        Assert.Equal("contract.pdf", detected[0].Filename);
        Assert.Same(dc, detected[0].OriginalContent);
        Assert.NotNull(detected[0].Data);
        Assert.Null(detected[0].Uri);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestDocumentKeyDerivation::test_filename_from_additional_properties
    public void DetectsDataContent_FillsFilenameFromAdditionalProperties_WhenNameMissing()
    {
        DataContent dc = new(PdfBytes, "application/pdf")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = "from-props.pdf" },
        };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("from-props.pdf", one.Filename);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestDocumentKeyDerivation::test_content_hash_fallback
    public void DetectsDataContent_SynthesizesFilename_WhenNeitherSourcePresent()
    {
        DataContent dc = new(PdfBytes, "application/pdf");
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));

        Assert.StartsWith("attachment-", one.Filename);
        Assert.EndsWith(".pdf", one.Filename);
        // 6 hex chars between "attachment-" and ".pdf"
        Assert.Matches("^attachment-[0-9a-f]{6}\\.pdf$", one.Filename);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestMimeSniffing::test_octet_stream_mp4_detected_and_stripped (re-sniff)
    public void DetectsDataContent_ResniffsWhenOctetStream()
    {
        // Caller incorrectly tagged a PNG as octet-stream; sniffer must override.
        DataContent dc = new(PngBytes, "application/octet-stream") { Name = "icon.png" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("image/png", one.ResolvedMediaType);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestMimeSniffing::test_octet_stream_unknown_binary_not_stripped
    public void SilentlySkips_OctetStreamWithUnknownBytes()
    {
        DataContent dc = new(new byte[] { 0xDE, 0xAD, 0xBE, 0xEF }, "application/octet-stream") { Name = "blob.bin" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        Assert.Empty(AttachmentDetector.Detect([msg]));
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestBinaryStripping::test_unsupported_files_left_in_place
    public void SilentlySkips_UnsupportedMediaType()
    {
        // text/plain is not in MEDIA_TYPE_ANALYZER_MAP — must skip per Python parity.
        DataContent dc = new(System.Text.Encoding.UTF8.GetBytes("hello"), "text/plain") { Name = "notes.txt" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        Assert.Empty(AttachmentDetector.Detect([msg]));
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestSupportedMediaTypes::test_zip_not_supported (URI variant)
    public void SilentlySkips_UriContentWithUnsupportedMediaType()
    {
        UriContent uc = new("https://example.com/data.json", "application/json");
        ChatMessage msg = new(ChatRole.User, [uc]);

        Assert.Empty(AttachmentDetector.Detect([msg]));
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestDocumentKeyDerivation::test_url_basename
    public void DetectsUriContent_WithFilenameFromUriPath()
    {
        UriContent uc = new("https://contoso.blob.core.windows.net/files/audio/callcenter.mp3", "audio/mpeg");
        ChatMessage msg = new(ChatRole.User, [uc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("audio/mpeg", one.ResolvedMediaType);
        Assert.Equal("callcenter.mp3", one.Filename);
        Assert.Null(one.Data);
        Assert.NotNull(one.Uri);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestDocumentKeyDerivation::test_filename_from_additional_properties (URI variant)
    public void DetectsUriContent_PrefersAdditionalPropertiesFilenameOverUriPath()
    {
        UriContent uc = new("https://contoso.blob.core.windows.net/files/something.dat", "audio/mpeg")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = "from-props.mp3" },
        };
        ChatMessage msg = new(ChatRole.User, [uc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("from-props.mp3", one.Filename);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestDocumentKeyDerivation::test_content_hash_fallback (URI variant)
    public void DetectsUriContent_SynthesizesFilename_WhenUriHasNoExtension()
    {
        UriContent uc = new("https://contoso.blob.core.windows.net/api/stream", "video/mp4");
        ChatMessage msg = new(ChatRole.User, [uc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Matches("^attachment-[0-9a-f]{6}\\.mp4$", one.Filename);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestBeforeRunMultiFile::test_two_files_both_analyzed (detection portion)
    public void DetectsMultipleAttachments_AcrossMessages()
    {
        ChatMessage msg1 = new(ChatRole.User,
        [
            new TextContent("First"),
            new DataContent(PdfBytes, "application/pdf") { Name = "first.pdf" },
        ]);
        ChatMessage msg2 = new(ChatRole.User,
        [
            new UriContent("https://example.com/movie.mp4", "video/mp4"),
        ]);

        DetectedAttachment[] detected = AttachmentDetector.Detect([msg1, msg2]).ToArray();

        Assert.Equal(2, detected.Length);
        Assert.Equal("first.pdf", detected[0].Filename);
        Assert.Equal("movie.mp4", detected[1].Filename);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestMimeSniffing::test_correct_mime_not_sniffed (sniff-failure fallback)
    public void ResolvedMediaType_FallsBackToSuppliedWhenSniffFails()
    {
        // Caller knows it's PDF; bytes don't (yet) carry the magic — supplied wins.
        DataContent dc = new(new byte[] { 0x01, 0x02 }, "application/pdf") { Name = "x.pdf" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("application/pdf", one.ResolvedMediaType);
    }
}
