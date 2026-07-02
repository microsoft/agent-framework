FROM python:3.12-slim

WORKDIR /app

# .NET 10 runtime is required by the `powerfx` package, which
# agent-framework-declarative uses to evaluate `=...` expressions in the
# workflow YAML (e.g. =Local.Triage.NeedsClarification). Without it,
# ConditionGroup evaluation raises and the workflow produces no output.
RUN apt-get update \
    && apt-get install -y --no-install-recommends wget ca-certificates libicu-dev \
    && wget -qO /tmp/dotnet-install.sh https://dot.net/v1/dotnet-install.sh \
    && chmod +x /tmp/dotnet-install.sh \
    && /tmp/dotnet-install.sh --runtime dotnet --channel 10.0 --install-dir /usr/share/dotnet \
    && ln -s /usr/share/dotnet/dotnet /usr/local/bin/dotnet \
    && rm -f /tmp/dotnet-install.sh \
    && rm -rf /var/lib/apt/lists/*

ENV DOTNET_ROOT=/usr/share/dotnet

COPY . user_agent/
WORKDIR /app/user_agent

RUN if [ -f requirements.txt ]; then \
        pip install -r requirements.txt; \
    else \
        echo "No requirements.txt found"; \
    fi

EXPOSE 8088

CMD ["python", "main.py"]
