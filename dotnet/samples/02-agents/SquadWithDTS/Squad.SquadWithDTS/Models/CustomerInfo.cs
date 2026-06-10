// Copyright (c) Microsoft. All rights reserved.
namespace Squad.SquadWithDTS.Models;

/// <summary>Customer account information fetched during deterministic enrichment.</summary>
internal sealed record CustomerInfo(
    string CustomerId,
    string Tier,
    string Sla,
    string ContactEmail
);
