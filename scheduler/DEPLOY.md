# Despliegue del motor de horarios — guía paso a paso

Esta app contiene **datos personales reales de estudiantes** (nombres, IDs, recomendaciones de consejeros). No la despliegues en infraestructura pública sin protección.

## Decisión rápida — ¿dónde alojarla?

| Plataforma | Repo privado | Disco persistente | Sin spin-down | Costo | Ideal para |
|---|---|---|---|---|---|
| **Streamlit Cloud Community** | ❌ requiere público | ❌ ephemero | ❌ duerme | gratis | Demos públicos no sensibles |
| **Render Starter** | ✅ | ✅ ($0.25/GB) | ✅ | $7/mes | **Recomendado** para uso del Colegio |
| **Render Free** | ✅ | ❌ | ❌ duerme tras 15 min | gratis | Pruebas del coordinador |
| **Railway** | ✅ | ✅ | depende del plan | $5+/mes | Alternativa a Render |
| **Local solamente** | n/a | ✅ | ✅ | gratis | Solo tú |

## Despliegue en Render (recomendado)

### Pre-requisitos

1. Cuenta en [render.com](https://render.com) (signup con GitHub)
2. Repo conectado a Render (puede ser privado)
3. Decidir un password fuerte para `APP_PASSWORD`

### Pasos

**1. Crear servicio web**

- Render Dashboard → **New** → **Blueprint**
- Conecta el repo `handoff_2026-04-26_continuation`
- Selecciona la rama (típicamente `main` o tu branch de release)
- Render detecta `scheduler/render.yaml` automáticamente

**2. Configurar variables de entorno**

En el dashboard del servicio, agrega:

| Variable | Valor | Por qué |
|---|---|---|
| `APP_PASSWORD` | (password fuerte) | Gate de acceso. SIN este var, la app es pública |
| `COLUMBUS_DB` | `/data/columbus.sqlite` | Ya en `render.yaml`. La SQLite vive en disco persistente |

**3. Deploy**

- Click **Manual Deploy** → **Deploy latest commit**
- Espera ~3 minutos (build + bootstrap)
- Render asigna URL `https://columbus-scheduler-XXXX.onrender.com`

**4. Validar**

- Abre la URL → deberías ver el password gate
- Ingresa el password → app aparece
- Prueba el flujo: Inputs → Solve → Compliance → Runs
- Revisa que la SQLite persiste recargando la página

### Costos esperados

- Servicio Starter: $7/mes
- Disco 1GB: $0.25/mes
- Total: **~$7.25/mes**

Para sólo pruebas, baja a Free plan y pierde la persistencia (la SQLite se reinicia con cada redeploy).

---

## Despliegue en Streamlit Cloud (alternativa)

⚠️ Requiere **repo público**. Los datos del Colegio NO deben estar en el repo. Verifica que `.gitignore` excluye:

```
scheduler/data/*.xlsx
scheduler/data/columbus*/
scheduler/data/*.sqlite
```

### Pasos

1. Repo público en GitHub
2. Cuenta en [share.streamlit.io](https://share.streamlit.io)
3. **New app** → seleccionar repo, branch, `scheduler/app.py` como entry point
4. **Advanced settings** → Secrets → agregar:
   ```toml
   APP_PASSWORD = "tu-password-aqui"
   ```
5. Deploy

### Limitaciones

- 1 GB RAM total — el solver de 509 estudiantes puede acercarse al límite con master_time alto
- Disco ephemero — la SQLite se reinicia con cada redeploy. Para persistencia real, necesitas un bucket S3/R2 montado vía wrappers
- App pública por URL incluso con password (cualquiera puede intentar)

---

## Hardening posterior (cuando esté en producción)

| Mejora | Cuándo | Cómo |
|---|---|---|
| Auth con cuentas | Si hay 2+ usuarios | `streamlit-authenticator` con users en YAML |
| Backup automático de la DB | Inmediato | Cron en Render que `cp /data/columbus.sqlite` a S3 cada noche |
| Logs estructurados | Cuando empieces a debuggear | `loguru` o `structlog` + Render log drains |
| Rate limiting | Si la URL se filtra | Cloudflare gratis frente del Render |
| Encriptación de DB | Antes de FERPA review | SQLite + SQLCipher |

---

## Local (sin despliegue)

```bash
cd scheduler
.venv/bin/streamlit run app.py
```

El gate solo se activa con `APP_PASSWORD` set. Sin el env var → app abierta directamente.
