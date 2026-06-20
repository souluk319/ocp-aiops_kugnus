FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY komsco_ai_gateway ./komsco_ai_gateway

EXPOSE 8443

USER 1001

CMD ["uvicorn", "komsco_ai_gateway.main:app", "--host", "0.0.0.0", "--port", "8443", "--ssl-certfile", "/var/run/secrets/tls/tls.crt", "--ssl-keyfile", "/var/run/secrets/tls/tls.key"]
