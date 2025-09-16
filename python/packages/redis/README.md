# Get Started with Microsoft Agent Framework Redis

Please install this package as the extra for `agent-framework`:

```bash
pip install agent-framework[redis]
```

## Memory Context Provider

The Redis context provider enables persistent memory capabilities for your agents, allowing them to remember user preferences and conversation context across different sessions and threads.

### Basic Usage Example

See the [Redis memory example](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/context_providers/redis/redis_memory.py) which demonstrates:

- Setting up an agent with Redis context provider, using the OpenAI API
- Teaching the agent user preferences
- Retrieving information using remembered context across new threads
- Persistent memory


### Installing and running Redis

You have 3 options to set-up Redis:

#### Option A: Local Redis with Docker**
docker run --name redis -p 6379:6379 -d redis:8.0.3

#### Option B: Redis Cloud
Get a free db at https://redis.io/cloud/

#### Option C: Azure Managed Redis
Here's a quickstart guide to create Azure Managed Redis for as low as $12 monthly: https://learn.microsoft.com/en-us/azure/redis/quickstart-create-managed-redis

#### Option D: 

Run this bash script (Works on either Linux or MacOS).

```
%%bash
set -euo pipefail

OS="$(uname -s)"

start_stack_daemon () {
  # Try to start Redis Stack in the background
  if command -v redis-stack-server >/dev/null 2>&1; then
    if pgrep -f redis-stack-server >/dev/null 2>&1; then
      echo "ℹ️ redis-stack-server already running."
    else
      echo "▶️  Starting redis-stack-server (daemonized)..."
      redis-stack-server --daemonize yes
    fi
  else
    echo "❌ redis-stack-server not found on PATH."
    exit 1
  fi
}

if [[ "$OS" == "Darwin" ]]; then
  echo "📦 macOS detected"
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is required on macOS. Install from https://brew.sh and re-run."
    exit 1
  fi

  # Make sure PATH covers both Apple Silicon and Intel installs
  export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

  # Install (idempotent)
  brew tap redis-stack/redis-stack || true
  if ! brew list --formula redis-stack >/dev/null 2>&1; then
    brew install redis-stack
  fi

  start_stack_daemon

elif [[ "$OS" == "Linux" ]]; then
  echo "📦 Linux detected"
  # Use sudo if we are not root
  if [[ "$(id -u)" -ne 0 ]]; then
    SUDO="sudo"
  else
    SUDO=""
  fi

  # Prereqs
  $SUDO apt-get update -y
  $SUDO apt-get install -y lsb-release curl gpg

  # Add Redis APT repo + key (idempotent)
  if [[ ! -f /usr/share/keyrings/redis-archive-keyring.gpg ]]; then
    curl -fsSL https://packages.redis.io/gpg | $SUDO gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
    $SUDO chmod 644 /usr/share/keyrings/redis-archive-keyring.gpg
  fi

  CODENAME="$(lsb_release -cs || echo bookworm)"
  echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb ${CODENAME} main" \
    | $SUDO tee /etc/apt/sources.list.d/redis.list >/dev/null

  $SUDO apt-get update -y
  $SUDO apt-get install -y redis-stack-server

  # Start without systemd
  start_stack_daemon

else
  echo "❌ Unsupported OS: $OS"
  exit 1
fi

# --- Verify & info ---
sleep 2
if command -v redis-cli >/dev/null 2>&1; then
  echo "PING -> $(redis-cli ping || echo 'failed')"
fi

pgrep -a redis || true
echo "✅ Redis Stack running on redis://localhost:6379"
echo "To stop gracefully: redis-cli shutdown"
echo "If that fails:     pkill -f redis-stack-server || true"
```


To uninstall on Linux:

```
#!/usr/bin/env bash
set -euo pipefail

PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

# Stop/disable service if present
if systemctl list-unit-files | grep -q "^redis-stack-server"; then
  echo "Stopping redis-stack-server service..."
  sudo systemctl stop redis-stack-server || true
  sudo systemctl disable redis-stack-server || true
fi

# Remove package
echo "Removing redis-stack-server package..."
sudo apt-get update -y
sudo apt-get remove -y redis-stack-server || true
# Remove configs and data owned by the package (purge)
if $PURGE; then
  sudo apt-get purge -y redis-stack-server || true
fi
sudo apt-get autoremove -y || true

# Remove the Redis APT repo & key (added during install)
if [[ -f /etc/apt/sources.list.d/redis.list ]]; then
  echo "Removing Redis APT source..."
  sudo rm -f /etc/apt/sources.list.d/redis.list
fi
if [[ -f /usr/share/keyrings/redis-archive-keyring.gpg ]]; then
  echo "Removing Redis APT keyring..."
  sudo rm -f /usr/share/keyrings/redis-archive-keyring.gpg
fi
sudo apt-get update -y

# Optional deep purge of residuals (data loss)
if $PURGE; then
  echo "Purging residual files (this will delete data/configs)..."
  # Typical locations used by redis/redis-stack packages
  sudo rm -rf /var/lib/redis* /var/log/redis* /etc/redis* 2>/dev/null || true
  # Some redis-stack installs keep binaries/configs in /opt/redis-stack
  sudo rm -rf /opt/redis-stack 2>/dev/null || true
fi

echo "✅ Linux uninstall complete."
echo "Note: Use --purge to remove data/configs and the repo key. This is irreversible."

```

To uninstall on MacOS:

```
#!/usr/bin/env bash
set -euo pipefail

PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

# Stop any running redis-stack-server started manually
if pgrep -f "redis-stack-server" >/dev/null; then
  echo "Stopping redis-stack-server..."
  pkill -f "redis-stack-server" || true
fi

if command -v brew >/dev/null 2>&1; then
  echo "Uninstalling Homebrew packages..."
  # Try both meta and sub-formulas in case either/both are present
  brew uninstall --ignore-dependencies --force redis-stack || true
  brew uninstall --ignore-dependencies --force redis-stack-server || true
  brew uninstall --cask --force redis-stack-redisinsight || true
  # Optional: untap (safe if not tapped)
  brew untap redis-stack/redis-stack || true
  brew cleanup
else
  echo "Homebrew not found; skipping brew uninstall."
fi

if $PURGE; then
  echo "Purging residual files (this will delete data/configs)..."
  # Common Homebrew data dirs (intel vs Apple Silicon)
  sudo rm -rf /usr/local/var/redis* /usr/local/etc/redis* 2>/dev/null || true
  sudo rm -rf /opt/homebrew/var/redis* /opt/homebrew/etc/redis* 2>/dev/null || true
  # Some redis-stack builds store config under /opt/redis-stack (seen in deployments)
  sudo rm -rf /opt/redis-stack 2>/dev/null || true
fi

echo "✅ macOS uninstall complete."
echo "Note: Use --purge to remove data/configs. Data loss is irreversible."
```