# Password Generation Guidelines

## General Rules

- Never reuse passwords across services.
- Always use cryptographically secure randomness (e.g., `random.SystemRandom()`).
- Avoid dictionary words, keyboard patterns, and personal information.

## Recommended Settings by Use Case

| Use Case              | Min Length | Character Set                          | Example                  |
|-----------------------|-----------|----------------------------------------|--------------------------|
| Web account           | 16        | Upper + lower + digits + symbols       | `G7!kQp@2xM#nW9$z`      |
| Database credential   | 24        | Upper + lower + digits + symbols       | `aR3$vK8!mN2@pQ7&xL5#wY` |
| Wi-Fi / network key   | 20        | Upper + lower + digits + symbols       | `Ht4&jL9!rP2#mK7@xQ`    |
| API key / token       | 32        | Upper + lower + digits (no symbols)    | `k8Rm3xQ7nW2pL9vT4jH6yA` |
| Encryption passphrase | 32        | Upper + lower + digits + symbols       | `Xp4!kR8@mN2#vQ7&jL9$wT` |

## Symbol Sets

- **Standard symbols**: `!@#$%^&*()-_=+`
- **Extended symbols**: `~`{}[]|;:'",.<>?/\`
- **Safe symbols** (URL/shell-safe): `!@#$&*-_=+`
- If the target system restricts symbols, use only the **safe** set.
