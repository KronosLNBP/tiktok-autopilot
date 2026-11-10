#!/usr/bin/env python3
"""Obtén tu TIKTOK_REFRESH_TOKEN (se hace UNA vez, en tu computadora).

  TIKTOK_CLIENT_KEY=xxx TIKTOK_CLIENT_SECRET=yyy REDIRECT_URI=https://... python auth_setup.py
"""
import os
import secrets
import urllib.parse

import requests

key = os.environ["TIKTOK_CLIENT_KEY"]
secret = os.environ["TIKTOK_CLIENT_SECRET"]
redirect = os.environ["REDIRECT_URI"]  # exactamente la registrada en tu app de TikTok
scopes = os.environ.get("SCOPES", "user.info.basic,video.upload,video.publish")

state = secrets.token_urlsafe(16)
url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(
    {"client_key": key, "scope": scopes, "response_type": "code", "redirect_uri": redirect, "state": state}
)
print("\n1) Abre este enlace, inicia sesión y autoriza la app:\n\n" + url)
print("\n2) TikTok te mandará a tu REDIRECT_URI (aunque la página dé error está bien).")
back = input("   Pega aquí la URL COMPLETA a la que llegaste:\n> ").strip()

q = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
if q.get("state", [""])[0] != state:
    raise SystemExit("El 'state' no coincide; vuelve a intentarlo.")

r = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={
        "client_key": key, "client_secret": secret, "code": q["code"][0],
        "grant_type": "authorization_code", "redirect_uri": redirect,
    },
    timeout=30,
).json()

if "refresh_token" not in r:
    raise SystemExit(f"Error: {r}")
print("\n✅ Listo. Guarda esto como secret TIKTOK_REFRESH_TOKEN en GitHub:\n")
print(r["refresh_token"])
print(f"\n(Scopes concedidos: {r.get('scope')} · expira en ~{r.get('refresh_expires_in', 0) // 86400} días)")
