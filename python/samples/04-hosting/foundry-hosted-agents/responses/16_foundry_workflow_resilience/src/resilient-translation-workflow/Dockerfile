FROM python:3.13-slim

WORKDIR /app

COPY . user_agent/
WORKDIR /app/user_agent

# requirements.txt references the private wheels by file so both container and
# Foundry code deployments install the same artifacts.
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -c "from azure.ai.agentserver.responses import ResponsesServerOptions; assert ResponsesServerOptions(resilient_background=True).resilient_background"

EXPOSE 8088

CMD ["python", "main.py"]
