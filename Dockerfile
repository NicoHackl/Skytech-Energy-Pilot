# Direkter Python-Basis-Build wie Skytech HEMS (kein HA-Basis-Image/s6),
# damit die Container-Umgebung inkl. SUPERVISOR_TOKEN an den Prozess durchgereicht wird.
FROM python:3.11-slim

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app
# Gebautes React-Bündel (docs/frontend.md): es wird im Repo mitgeliefert, damit im Image
# kein Node laufen muss — der HA-Supervisor baut auf der Zielhardware, dort wäre ein
# npm-Build je Installation teuer (und auf armv7 spürbar langsam).
COPY frontend/dist /app/energy_pilot/web/frontend
EXPOSE 8098

CMD ["python3", "main.py"]
