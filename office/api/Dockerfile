FROM python:3.12-alpine
WORKDIR /app
RUN apk add --no-cache tzdata && addgroup -g 10001 portal && adduser -D -u 10001 -G portal portal && mkdir -p /data && chown portal:portal /data && chmod 700 /data
COPY server.py /app/server.py
USER 10001:10001
ENV DATA_DIR=/data PYTHONUNBUFFERED=1 TZ=Europe/Berlin
EXPOSE 8000
CMD ["python", "-u", "/app/server.py"]
