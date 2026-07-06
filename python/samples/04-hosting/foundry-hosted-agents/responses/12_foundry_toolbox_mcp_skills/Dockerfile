FROM python:3.12-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . user_agent/
WORKDIR /app/user_agent

RUN if [ -f requirements.txt ]; then \
        pip install -r requirements.txt; \
    else \
        echo "No requirements.txt found"; \
    fi

EXPOSE 8088

CMD ["python", "main.py"]
