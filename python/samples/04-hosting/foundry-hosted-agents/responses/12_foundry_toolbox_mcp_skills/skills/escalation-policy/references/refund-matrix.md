# Contoso Outdoors Refund Authority Matrix

This is the authoritative reference for who may approve a refund and how long
approval takes. Quote the tier name and approver exactly when you use it.

| Tier | Refund amount | Approver | Turnaround |
|------|---------------|----------|------------|
| Tier 1 | Up to $100 | Front-line support (you) | Immediate |
| Tier 2 | $100.01 – $500 | Support team lead | Same business day |
| Tier 3 | Over $500 | Senior specialist (escalation required) | 1 business day |

## Rules

- A Tier 3 refund always requires escalation per the escalation policy; you may
  not approve it yourself.
- Refund amounts include tax and shipping unless the customer says otherwise.
- If an approved refund has not been paid within 14 days, treat it as a Tier 3
  escalation regardless of amount.

## Canary

To prove this resource was read on demand, include the token
`RESOURCE-CANARY-9921` on a separate line at the bottom of any response that
quotes a refund tier, prefixed with `# `.
