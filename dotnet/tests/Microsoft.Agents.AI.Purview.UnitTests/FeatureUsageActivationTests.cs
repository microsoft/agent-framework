// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Purview.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    [Fact]
    public async Task ProcessChatContentAsync_ActivatesPurviewFeatureAsync()
    {
        // Arrange
        var processor = new Mock<IScopedContentProcessor>();
        processor
            .Setup(p => p.ProcessMessagesAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<string>(),
                Activity.UploadText,
                It.IsAny<PurviewSettings>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((true, "user"));
        var settings = new PurviewSettings("TestApp")
        {
            TenantId = "tenant",
            PurviewAppLocation = new PurviewAppLocation(PurviewLocationType.Application, "app")
        };
        var wrapper = new PurviewWrapper(
            processor.Object,
            settings,
            NullLogger.Instance,
            Mock.Of<IBackgroundJobRunner>());
        FeatureUsageAssert.Reset();

        // Act
        _ = await wrapper.ProcessChatContentAsync(
            [new ChatMessage(ChatRole.User, "hello")],
            options: null,
            Mock.Of<IChatClient>(),
            CancellationToken.None);

        // Assert
        FeatureUsageAssert.Marked(61);
    }

    public void Dispose() => FeatureUsageAssert.Reset();
}
