FROM python:3.12-slim

WORKDIR /app/user_agent

COPY wheels/ /tmp/wheels/
COPY requirements.txt .
RUN pip install --no-cache-dir --find-links /tmp/wheels/ -r requirements.txt && rm -rf /tmp/wheels/

COPY . .

RUN useradd -r appuser
USER appuser

EXPOSE 8088

CMD ["python", "main.py"]