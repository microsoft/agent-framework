// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 3 / dev plan task 3.1 — MIME byte-signature detection.
/// </summary>
public sealed class MimeSnifferTests
{
    [Fact]
    public void Detects_Pdf()
        => Assert.Equal("application/pdf", MimeSniffer.Detect([0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x37]));

    [Fact]
    public void Detects_Png()
        => Assert.Equal("image/png", MimeSniffer.Detect([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00]));

    [Fact]
    public void Detects_Jpeg()
        => Assert.Equal("image/jpeg", MimeSniffer.Detect([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10]));

    [Fact]
    public void Detects_Mp3_Id3()
        => Assert.Equal("audio/mpeg", MimeSniffer.Detect([0x49, 0x44, 0x33, 0x03, 0x00, 0x00]));

    [Fact]
    public void Detects_Mp3_FrameSync()
        => Assert.Equal("audio/mpeg", MimeSniffer.Detect([0xFF, 0xFB, 0x90, 0x00]));

    [Fact]
    public void Detects_Mp4()
    {
        // Bytes 4..8 = "ftyp"
        byte[] head = [0x00, 0x00, 0x00, 0x20, (byte)'f', (byte)'t', (byte)'y', (byte)'p', (byte)'i', (byte)'s', (byte)'o', (byte)'m'];
        Assert.Equal("video/mp4", MimeSniffer.Detect(head));
    }

    [Fact]
    public void Detects_Wav()
    {
        // "RIFF" + 4-byte size + "WAVE"
        byte[] head = [(byte)'R', (byte)'I', (byte)'F', (byte)'F', 0x24, 0x00, 0x00, 0x00, (byte)'W', (byte)'A', (byte)'V', (byte)'E'];
        Assert.Equal("audio/wav", MimeSniffer.Detect(head));
    }

    [Fact]
    public void ReturnsNullForUnknownSignature()
    {
        byte[] head = [0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0xBA, 0xBE];
        Assert.Null(MimeSniffer.Detect(head));
    }

    [Fact]
    public void ReturnsNullForEmpty()
        => Assert.Null(MimeSniffer.Detect(ReadOnlySpan<byte>.Empty));

    [Fact]
    public void DoesNotMisdetect_ShortPdfPrefix()
    {
        // Only first byte of PDF magic — must NOT match.
        byte[] head = [0x25];
        Assert.Null(MimeSniffer.Detect(head));
    }
}
