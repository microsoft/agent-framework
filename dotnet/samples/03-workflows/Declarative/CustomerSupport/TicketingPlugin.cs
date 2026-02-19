// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;

namespace Demo.Workflows.Declarative.CustomerSupport;

internal sealed class TicketingPlugin
{
    private readonly Dictionary<string, TicketItem> _ticketStore = [];

    [Description("Retrieve a ticket by identifier from Azure DevOps.")]
    public TicketItem? GetTicket(string id)
    {
        Trace(nameof(GetTicket));

        this._ticketStore.TryGetValue(id, out TicketItem? ticket);

        return ticket;
    }

    [Description("Create a ticket in Azure DevOps and return its identifier.")]
    public string CreateTicket(string subject, string description, string notes)
    {
        Trace(nameof(CreateTicket));

        TicketItem ticket = new()
        {
            Subject = subject,
            Description = description,
            Notes = notes,
            Id = Guid.NewGuid().ToString("N"),
        };

        this._ticketStore[ticket.Id] = ticket;

        return ticket.Id;
    }

    [Description("Resolve an existing ticket in Azure DevOps given its identifier.")]
    public void ResolveTicket(string id, string resolutionSummary)
    {
        Trace(nameof(ResolveTicket));

        if (this._ticketStore.TryGetValue(id, out TicketItem? ticket))
        {
            ticket.Status = TicketStatus.Resolved;
        }
    }

    [Description("Send an email notification to escalate ticket engagement.")]
    public void SendNotification(string id, string email, string cc, string body)
    {
        Trace(nameof(SendNotification));
    }

    private static void Trace(string functionName)
    {
        Console.ForegroundColor = ConsoleColor.DarkMagenta;
        try
        {
            Console.WriteLine($"\nFUNCTION: {functionName}");
        }
        finally
        {
            Console.ResetColor();
        }
    }

    public enum TicketStatus
    {
        Open,
        InProgress,
        Resolved,
        Closed,
    }

    public sealed class TicketItem
    {
        public TicketStatus Status { get; set; } = TicketStatus.Open;
        public string Subject { get; init; } = string.Empty;
        public string Id { get; init; } = string.Empty;
        public string Description { get; init; } = string.Empty;
        public string Notes { get; init; } = string.Empty;
    }
}
