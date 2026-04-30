# Despliegue del motor de horarios

La app contiene **datos personales reales de estudiantes** (nombres, IDs,
recomendaciones de consejeros). Solo debe correr en infraestructura
controlada por el Colegio.

## Opciones — comparación rápida

| Plataforma | Datos privados | Costo | Esfuerzo | Ideal para |
|---|---|---|---|---|
| **Servidor interno (Docker)** | ✅ red privada | infra existente | ~30 min | **Recomendado** — Colegio |
| **Servidor interno (Python)** | ✅ red privada | infra existente | ~15 min | Si el servidor no tiene Docker |
| Render Starter | ⚠️ red pública | $7/mes | ~30 min | Acceso remoto controlado |
| Streamlit Cloud Community | ❌ requiere repo público | gratis | n/a | NO usar — datos privados |

---

## Opción 1 — Servidor interno con Docker (recomendado)

### Requisitos en el servidor

- Linux (Ubuntu/Debian/CentOS) o macOS
- Docker 20.10+
- Docker Compose v2
- Puerto disponible (default 8501)
- Al menos 1GB RAM libre, 2GB de disco

### Pasos

```bash
# 1. Clonar el repo en el servidor (red privada o VPN)
git clone <ruta-al-repo> columbus-scheduler
cd columbus-scheduler/scheduler

# 2. Configurar variables de entorno
cp .env.example .env
# editar .env y poner APP_PASSWORD a algo fuerte (16+ caracteres)
nano .env

# 3. Build + start
docker compose up -d --build

# 4. Verificar
docker compose ps
# Debería mostrar 'columbus-scheduler' running y healthy

# 5. Test desde el navegador
# http://<ip-del-servidor>:8501
```

### Operación

| Acción | Comando |
|---|---|
| Ver logs | `docker compose logs -f` |
| Restart | `docker compose restart` |
| Stop | `docker compose down` |
| Update (pull + rebuild) | `git pull && docker compose up -d --build` |
| Backup BD | `docker compose exec scheduler sh -c "cp /data/columbus.sqlite /data/backup-$(date +%Y%m%d).sqlite"` |
| Inspect BD | `docker compose exec scheduler sqlite3 /data/columbus.sqlite "SELECT * FROM run"` |

### Persistencia

La SQLite (todos los runs, bundles, configs) vive en el volumen Docker
`columbus-data`. Sobrevive a `docker compose down/up`. Para backup
externo, copia periódicamente el archivo `/data/columbus.sqlite` a un
NAS o tape.

### Cuándo cambiar APP_PASSWORD

- Cuando se va alguien con acceso
- Cada semestre como buena práctica
- Cambiar el `.env` y `docker compose restart`

---

## Opción 2 — Servidor interno con Python directo (sin Docker)

Si el servidor no tiene Docker, corre Streamlit directo:

```bash
git clone <ruta-al-repo> columbus-scheduler
cd columbus-scheduler/scheduler

# Crear venv
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Variables de entorno
export APP_PASSWORD="tu-password-fuerte-aqui"
export COLUMBUS_DB="/var/lib/columbus/columbus.sqlite"

# Crear directorio para BD
sudo mkdir -p /var/lib/columbus
sudo chown $USER /var/lib/columbus

# Correr (en foreground, para probar)
.venv/bin/streamlit run app.py --server.port 8501 --server.headless true
```

Para correrlo como **servicio systemd** que sobrevive reboots:

```ini
# /etc/systemd/system/columbus-scheduler.service
[Unit]
Description=Columbus Scheduling Engine
After=network.target

[Service]
Type=simple
User=columbus
WorkingDirectory=/opt/columbus-scheduler/scheduler
Environment="APP_PASSWORD=tu-password-fuerte-aqui"
Environment="COLUMBUS_DB=/var/lib/columbus/columbus.sqlite"
ExecStart=/opt/columbus-scheduler/scheduler/.venv/bin/streamlit run app.py \
  --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now columbus-scheduler
sudo systemctl status columbus-scheduler
journalctl -u columbus-scheduler -f
```

---

## Opción 3 — Render (acceso remoto)

⚠️ Solo si el personal necesita acceso desde fuera de la red del Colegio
y no hay VPN. La app sirve datos reales por HTTPS público con password.

Ver `render.yaml` (ya en el repo). Pasos:

1. Cuenta en [render.com](https://render.com)
2. Conecta el repo (privado funciona en plan Starter)
3. Render Dashboard → New → Blueprint → selecciona el repo
4. Configura env vars: `APP_PASSWORD` (manualmente)
5. Manual Deploy → Deploy latest commit

Costo: $7/mes (Starter) + $0.25/mes (disco 1GB) = **~$7.25/mes**

---

## Configuración de red interna recomendada

### Acceso solo desde la LAN del Colegio

```
[Coordinador's PC] ─┐
                    ├─→ [Servidor interno :8501] ─→ [Streamlit app]
[Otros PCs LAN]  ───┘
```

- **Sin reverse proxy:** funciona out-of-the-box, acceso por IP del servidor
- **Con reverse proxy (nginx/caddy):** dale un dominio interno tipo `scheduler.colegio.local` con HTTPS auto-firmado
- **Con VPN:** el coordinador conecta a la VPN del Colegio desde casa, accede igual

### Ejemplo nginx en frente

```nginx
server {
    listen 443 ssl;
    server_name scheduler.colegio.local;

    ssl_certificate     /etc/letsencrypt/live/scheduler/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/scheduler/privkey.pem;

    # Streamlit necesita websockets
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }
}
```

---

## Hardening posterior (opcional)

| Mejora | Cuándo | Cómo |
|---|---|---|
| Backup automático nocturno | Inmediato | Cron del servidor que copia `/data/columbus.sqlite` a NAS |
| Auth con cuentas (SSO) | Cuando haya 5+ usuarios | `streamlit-authenticator` con LDAP del Colegio |
| Rate limiting | Si se expone vía internet | nginx `limit_req` en frente |
| Encriptación de BD | Antes de auditoría FERPA | Cambiar SQLite por SQLCipher (requiere wrapper) |
| Logs centralizados | Cuando sea producción crítica | Render log drains a Loki/Splunk |

---

## Local (desarrollo)

```bash
cd scheduler
.venv/bin/streamlit run app.py
```

Sin `APP_PASSWORD` la app es abierta — útil para iterar.
