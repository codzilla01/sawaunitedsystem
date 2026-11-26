FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SCANNER_PORT=8080
WORKDIR /app
COPY deploy/scanner/server.py /app/server.py
RUN useradd --system --uid 10002 --no-create-home scanner
USER scanner
EXPOSE 8080
CMD ["python", "/app/server.py"]
