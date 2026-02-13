# Purview Package (agent-framework-purview)

Integration with Microsoft Purview for data governance and policy enforcement.

## Main Classes

### Middleware

- **`PurviewPolicyMiddleware`** - Agent middleware for Purview policy enforcement
- **`PurviewChatPolicyMiddleware`** - Chat-level middleware for policy enforcement

### Configuration

- **`PurviewSettings`** - Pydantic settings for Purview configuration
- **`PurviewAppLocation`** / **`PurviewLocationType`** - Location configuration

### Caching

- **`CacheProvider`** - Cache provider for Purview policy caching

### Exceptions

- **`PurviewAuthenticationError`** - Authentication failures
- **`PurviewRateLimitError`** - Rate limit exceeded
- **`PurviewRequestError`** / **`PurviewServiceError`** - Request/service errors
- **`PurviewPaymentRequiredError`** - Payment required

## Usage

```python
from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings

settings = PurviewSettings(...)
middleware = PurviewPolicyMiddleware(settings=settings)
agent = Agent(..., middleware=[middleware])
```

## Import Path

```python
from agent_framework.microsoft import PurviewPolicyMiddleware
# or directly:
from agent_framework_purview import PurviewPolicyMiddleware
```
