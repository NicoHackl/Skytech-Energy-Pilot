# Default-Basis erlaubt einen lokalen/CI-Smoke-Build ohne HA-Basis-Image
ARG BUILD_FROM=python:3.11-alpine
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Python-Laufzeit sicherstellen (HA-Basis-Images bringen sie nicht mit)
RUN command -v python3 >/dev/null 2>&1 || apk add --no-cache python3 py3-pip

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
