// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class OAuthConsentEmissionTests
{
    private static ResponseEventStream CreateTestStream()
    {
        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        var request = new CreateResponse { Model = "test-model" };
        return new ResponseEventStream(mockContext.Object, request);
    }

    [Fact]
    public void EmitOAuthConsentRequest_EmitsOAuthConsentRequestItem_NotMcpApproval()
    {
        // Arrange
        const string ConsentUrl = "https://login.microsoftonline.com/consent?data=abc";
        const string ServerLabel = "outlook_mail";
        var stream = CreateTestStream();

        // Act: emit the consent request (added → done).
        List<ResponseStreamEvent> events =
            AgentFrameworkResponseHandler.EmitOAuthConsentRequest(stream, ServerLabel, ConsentUrl).ToList();

        // Assert: exactly an output_item.added followed by output_item.done, carrying an
        // oauth_consent_request item with the consent link and server label. A valid wire id is
        // required by AddOutputItem; if the generated id were malformed this call would have thrown.
        Assert.Equal(2, events.Count);
        var added = Assert.IsType<ResponseOutputItemAddedEvent>(events[0]);
        var done = Assert.IsType<ResponseOutputItemDoneEvent>(events[1]);

        var addedItem = Assert.IsType<OAuthConsentRequestOutputItem>(added.Item);
        Assert.Equal(ConsentUrl, addedItem.ConsentLink);
        Assert.Equal(ServerLabel, addedItem.ServerLabel);
        Assert.StartsWith("oacr_", addedItem.Id);

        var doneItem = Assert.IsType<OAuthConsentRequestOutputItem>(done.Item);
        Assert.Equal(addedItem.Id, doneItem.Id);
    }
}
