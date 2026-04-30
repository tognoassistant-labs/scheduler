# Multi-stage Dockerfile para deploy interno del Columbus Scheduler.
#
# Build:
#   docker build -t columbus-scheduler:v4.27 -f scheduler/Dockerfile scheduler/
#
# Run (con persistencia + password):
#   docker run -d --name columbus \
#     -p 8501:8501 \
#     -v columbus-data:/data \
#     -e COLUMBUS_DB=/data/columbus.sqlite \
#     -e APP_PASSWORD=<password-fuerte> \
#     columbus-scheduler:v4.27
#
# El volumen `columbus-data` persiste runs entre reinicios.

# ---- Stage 1: builder — instala deps en un layer cacheable ----
FROM python:3.12-slim AS builder

WORKDIR /build

# OS deps que necesita ortools (libgomp para OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# ---- Stage 2: runtime — solo lo necesario para correr ----
FROM python:3.12-slim

# Runtime deps (libgomp1 lo necesita ortools en runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root para correr la app
RUN useradd --create-home --shell /bin/bash app
USER app

# Copiar deps instaladas en stage builder
COPY --from=builder --chown=app:app /root/.local /home/app/.local

# Path para el binario streamlit del usuario
ENV PATH=/home/app/.local/bin:$PATH

WORKDIR /app
COPY --chown=app:app . /app

# Persistencia: la BD vive en /data, montar como volumen
ENV COLUMBUS_DB=/data/columbus.sqlite
RUN mkdir -p /data && chmod 777 /data || true

EXPOSE 8501

# Health check para load balancers / orquestadores
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
