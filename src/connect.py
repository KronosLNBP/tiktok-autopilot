"""Termina la conexión de una cuenta de TikTok desde GitHub Actions.

Recibe la URL de callback (con ?code=...), la cambia por tokens, guarda el
refresh token como secret del repo y publica solo el nombre y avatar en docs/account.json.
Nunca imprime tokens (el repo y sus logs son públicos).
"""
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
REDIRECT = "https://kronoslnbp.github.io/tiktok-autopilot/callback/"


def mask(v: str):
    if v:
        print(f"::add-mask::{v}")


def main():
    raw = os.environ.get("CALLBACK_URL", "").strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
    code = (q.get("code") or [raw if raw and "://" not in raw else ""])[0]
    if not code:
        sys.exit("❌ No encontré el parámetro 'code' en la URL. Pega la dirección completa de la página de callback.")
    mask(code)

    r = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": os.environ.get("REDIRECT_URI", REDIRECT),
        },
        timeout=30,
    ).json()
    if "refresh_token" not in r:
        sys.exit(f"❌ TikTok rechazó el código (¿expiró o ya se usó? Vuelve a conectar desde el sitio): "
                 f"{r.get('error')} {r.get('error_description')}")
    mask(r["access_token"])
    mask(r["refresh_token"])
    print(f"🔐 Permisos concedidos: {r.get('scope')}")

    u = requests.get(
        "https://open.tiktokapis.com/v2/user/info/",
        params={"fields": "open_id,display_name,avatar_url"},
        headers={"Authorization": f"Bearer {r['access_token']}"},
        timeout=30,
    ).json().get("data", {}).get("user", {})
    print(f"👤 Cuenta conectada: {u.get('display_name')}")

    if not os.environ.get("GH_PAT"):
        sys.exit("❌ Falta el secret GH_PAT (token de GitHub con permiso 'Secrets: Read and write') para guardar la conexión.")
    subprocess.run(
        ["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--repo", os.environ["GITHUB_REPOSITORY"], "--body", r["refresh_token"]],
        check=True, env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]},
    )
    print("✅ Refresh token guardado en GitHub Secrets")

    (ROOT / "docs" / "account.json").write_text(json.dumps({
        "display_name": u.get("display_name"),
        "avatar_url": u.get("avatar_url"),
        "scopes": r.get("scope"),
        "connected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
