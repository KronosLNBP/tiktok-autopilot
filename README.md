# 🎬 TikTok Autopilot

Pipeline en GitHub que **crea videos de TikTok, los sube y lleva el registro** sin que hagas nada a diario.

```
 Claude genera ideas ──► content/queue.yaml ──► render (Python + ffmpeg)
                                                       │
       content/posted.json ◄── commit automático ◄── TikTok API (borrador o publicación directa)
```

- **Diario a las 19:17 (CDMX)** el workflow *Publicar en TikTok* toma la siguiente idea pendiente, genera el video 1080×1920 y lo sube.
- Si quedan menos de 5 ideas, **Claude escribe más** según el nicho de `config.yaml`.
- Cada cambio en la cola dispara *Vista previa*: los videos quedan en *Actions → Artifacts* para que los revises.
- Todo queda versionado en git: qué se publicó, cuándo, con qué caption y su `publish_id`.

## Estructura

| Archivo | Para qué |
|---|---|
| `config.yaml` | Nicho, tono, hashtags, colores, modo de publicación |
| `content/queue.yaml` | Cola de ideas (hook, puntos, CTA, caption) |
| `content/posted.json` | Historial de lo subido |
| `assets/music/` | Pon aquí tus `.mp3` (con licencia). Si está vacío, se genera música sintética |
| `cli.py` | `list`, `render`, `ideas`, `publish`, `skip` |
| `auth_setup.py` | Obtiene tu refresh token de TikTok (una vez) |

## Configuración (una sola vez, ~20 min)

### 1. Sube el repo a GitHub
```bash
gh repo create tiktok-autopilot --private --source . --push
```

### 2. Crea tu app en TikTok for Developers
1. Entra a <https://developers.tiktok.com> → **Manage apps → Connect an app**.
2. Agrega el producto **Content Posting API** y activa los scopes `video.upload` (borradores) y `video.publish` (publicación directa). También `user.info.basic` (Login Kit).
3. En **Login Kit → Redirect URI** registra una URL https tuya, por ejemplo `https://autopilot.kronosmedicine.com.mx/callback/` (no necesita existir).
4. Copia el **Client key** y **Client secret**.

> ⚠️ Mientras la app no pase la **auditoría** de TikTok, los posts directos solo pueden ser **privados (SELF_ONLY)**. Por eso el modo por defecto es `draft`: el video llega a tu bandeja de TikTok y tú le das *Publicar* (público) desde el celular. Cuando TikTok apruebe la auditoría, cambia a `mode: direct` y `privacy_level: PUBLIC_TO_EVERYONE`.

### 3. Obtén el refresh token (en tu compu)
```bash
pip install -r requirements.txt
TIKTOK_CLIENT_KEY=xxx TIKTOK_CLIENT_SECRET=yyy \
REDIRECT_URI=https://autopilot.kronosmedicine.com.mx/callback/ \
python auth_setup.py
```

### 4. Guarda los secrets en GitHub
```bash
gh secret set TIKTOK_CLIENT_KEY
gh secret set TIKTOK_CLIENT_SECRET
gh secret set TIKTOK_REFRESH_TOKEN
gh secret set ANTHROPIC_API_KEY   # opcional: ideas automáticas (console.anthropic.com)
gh secret set GH_PAT              # opcional: token con permiso "Secrets: write" para rotar el refresh token solo
```

### 5. Prueba
*Actions → Publicar en TikTok → Run workflow* (marca **dry run** la primera vez para solo ver el video).

## Uso diario

- **Agregar ideas a mano:** edita `content/queue.yaml` desde GitHub (incluso desde el celular) y haz commit.
- **Saltar una idea:** `python cli.py skip ID` o cambia su `status` a `skip`.
- **Cambiar frecuencia:** edita el `cron` en `.github/workflows/publish.yml` (p. ej. `"17 1,19 * * *"` = 2 veces al día) o `videos_per_run`.
- **Cambiar estilo:** colores, tiempos y tu `@handle` en `config.yaml → style`.
- **Ver estado:** `python cli.py list` o revisa `content/posted.json`.

## Buenas prácticas
- Revisa las ideas que genera Claude antes de que salgan (la *Vista previa* sirve para eso).
- No uses música comercial sin licencia; usa tu biblioteca libre de derechos en `assets/music/`.
- TikTok limita cuántos posts por día acepta la API por cuenta; 1–3 al día es seguro.
