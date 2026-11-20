# ==============================================================================
# Dockerfile per Fatture Locali & HACCP
# Krügel – Lavis & Cafè L’Incontro – Pergine
# ==============================================================================

FROM python:3.12-slim

# Ottimizzazioni runtime Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    DB_PATH=/data/fatture_locali.db \
    BACKUP_DIR=/backups

# Directory di lavoro dell'applicazione
WORKDIR /app

# Installa curl per l'healthcheck del container
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installa dipendenze Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice applicativo
COPY app /app/app
COPY demo_fatture /app/demo_fatture
COPY backup.py /app/backup.py

# Crea le cartelle per i dati persistenti e i backup
RUN mkdir -p /data /backups

# Volumi per rendere persistente il database e i backup automatici
VOLUME ["/data", "/backups"]

# Porta di ascolto
EXPOSE 8000

# Controllo periodico integrità del servizio
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Avvio con Uvicorn multi-worker per accesso contemporaneo da più tablet e PC
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
