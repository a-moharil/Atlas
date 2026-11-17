FROM python:3.12-slim
WORKDIR /app
COPY *.py *.json ./
COPY static ./static
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OBS_DB=/storage/observatory.sqlite3
RUN mkdir -p /storage && chown -R 10001:10001 /storage /app
USER 10001
EXPOSE 8765
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8765"]
