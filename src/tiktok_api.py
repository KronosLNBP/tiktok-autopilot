"""Cliente mínimo para la TikTok Content Posting API (v2)."""
from __future__ import annotations

import math
import os
import subprocess
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"
CHUNK = 10 * 1024 * 1024  # 10 MB (TikTok acepta 5–64 MB por chunk)


class TikTokError(RuntimeError):
    pass


def _check(r: requests.Response) -> dict:
    try:
        body = r.json()
    except ValueError:
        raise TikTokError(f"HTTP {r.status_code}: {r.text[:300]}")
    err = body.get("error", {})
    if r.status_code >= 400 or (err and err.get("code") not in (None, "ok")):
        raise TikTokError(f"{err.get('code')}: {err.get('message')} (log_id={err.get('log_id')})")
    return body.get("data", body)


def refresh_access_token() -> str:
    """Cambia el refresh token (válido ~1 año) por un access token (24 h)."""
    r = requests.post(
        f"{API}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
        },
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise TikTokError(f"No se pudo refrescar el token: {data}")
    new_rt = data.get("refresh_token")
    if new_rt and new_rt != os.environ["TIKTOK_REFRESH_TOKEN"]:
        _rotate_secret(new_rt)
    return data["access_token"]


def _rotate_secret(new_rt: str) -> None:
    """Si TikTok rota el refresh token, lo guarda en los secrets del repo (requiere GH_PAT)."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (repo and os.environ.get("GH_PAT")):
        print("⚠️  TikTok entregó un refresh token nuevo; configura GH_PAT para guardarlo solo.")
        return
    subprocess.run(
        ["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--repo", repo, "--body", new_rt],
        check=True,
        env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]},
    )
    print("🔑 Refresh token rotado y guardado en GitHub Secrets.")


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}


def creator_info(token: str) -> dict:
    return _check(requests.post(f"{API}/post/publish/creator_info/query/", headers=_headers(token), timeout=30))


def _source_info(size: int) -> dict:
    if size <= CHUNK:
        return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    count = max(1, size // CHUNK)  # el último chunk absorbe el resto
    return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": CHUNK, "total_chunk_count": count}


def _upload_file(upload_url: str, path: Path, src: dict) -> None:
    size, chunk, count = src["video_size"], src["chunk_size"], src["total_chunk_count"]
    with open(path, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            part = f.read(end - start + 1)
            r = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(part)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                },
                data=part,
                timeout=300,
            )
            if r.status_code not in (200, 201, 206):
                raise TikTokError(f"Fallo subiendo chunk {i + 1}/{count}: HTTP {r.status_code} {r.text[:200]}")


def upload(token: str, path: Path, caption: str, pub_cfg: dict) -> str:
    """Sube el video. mode=draft → bandeja de entrada; mode=direct → publica."""
    src = _source_info(path.stat().st_size)
    if pub_cfg.get("mode") == "direct":
        info = creator_info(token)
        allowed = info.get("privacy_level_options", [])
        privacy = pub_cfg.get("privacy_level", "SELF_ONLY")
        if allowed and privacy not in allowed:
            print(f"⚠️  {privacy} no permitido para esta cuenta/app; usando {allowed[0]}")
            privacy = allowed[0]
        body = {
            "post_info": {
                "title": caption[:2200],
                "privacy_level": privacy,
                "disable_comment": pub_cfg.get("disable_comment", False),
                "disable_duet": pub_cfg.get("disable_duet", False),
                "disable_stitch": pub_cfg.get("disable_stitch", False),
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": src,
        }
        url = f"{API}/post/publish/video/init/"
    else:
        body = {"source_info": src}
        url = f"{API}/post/publish/inbox/video/init/"

    data = _check(requests.post(url, headers=_headers(token), json=body, timeout=30))
    _upload_file(data["upload_url"], path, src)
    return data["publish_id"]


def wait_status(token: str, publish_id: str, timeout_s: int = 300) -> dict:
    final = {"PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED"}
    deadline = time.time() + timeout_s
    status = {}
    while time.time() < deadline:
        status = _check(
            requests.post(
                f"{API}/post/publish/status/fetch/",
                headers=_headers(token),
                json={"publish_id": publish_id},
                timeout=30,
            )
        )
        print(f"   estado: {status.get('status')}")
        if status.get("status") in final:
            return status
        time.sleep(8)
    return status
