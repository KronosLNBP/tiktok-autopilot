#!/usr/bin/env python3
"""TikTok Autopilot — CLI.

  python cli.py list                 # ver la cola
  python cli.py render [ID|next|all] # generar videos en output/
  python cli.py ideas [--force]      # pedir ideas nuevas a Claude (si faltan)
  python cli.py publish              # ciclo completo: ideas → render → subir → registrar
  python cli.py skip ID              # saltar una idea
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from render import render  # noqa: E402

QUEUE = ROOT / "content" / "queue.yaml"
POSTED = ROOT / "content" / "posted.json"
OUT = ROOT / "output"


def load_cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_queue() -> list[dict]:
    return yaml.safe_load(QUEUE.read_text()) or []


def save_queue(q: list[dict]) -> None:
    header = "# Cola de videos. status: pending → uploaded/published (o skip)\n"
    QUEUE.write_text(header + yaml.safe_dump(q, allow_unicode=True, sort_keys=False, width=1000))


def caption_for(item: dict, cfg: dict) -> str:
    tags = list(dict.fromkeys(item.get("hashtags", []) + cfg["default_hashtags"]))
    return f"{item.get('caption', item['hook'])} {' '.join(tags)}".strip()


def pending(q):
    return [i for i in q if i.get("status", "pending") in ("pending", "rendered")]


def cmd_list():
    q = load_queue()
    for i in q:
        print(f"[{i.get('status', 'pending'):>9}] {i['id']}: {i['hook']}")
    print(f"\n{len(pending(q))} pendientes · {len(json.loads(POSTED.read_text()))} publicados")


def cmd_ideas(force=False):
    from ideas import generate

    cfg, q = load_cfg(), load_queue()
    if not cfg["ideas"]["enabled"]:
        return
    if not force and len(pending(q)) >= cfg["ideas"]["min_pending"]:
        print(f"✅ Hay {len(pending(q))} ideas pendientes; no hace falta generar.")
        return
    new = generate(cfg, [i["id"] for i in q])
    if new:
        save_queue(q + new)


def cmd_render(target="next"):
    cfg, q = load_cfg(), load_queue()
    if target == "all":
        items = pending(q)
    elif target == "next":
        items = pending(q)[:1]
    else:
        items = [i for i in q if i["id"] == target]
    if not items:
        print("No hay nada que renderizar.")
        return []
    paths = []
    for it in items:
        print(f"🎬 Renderizando {it['id']}…")
        paths.append(render(it, cfg, OUT / f"{it['id']}.mp4"))
        print(f"   → {paths[-1]}")
    return paths


def cmd_publish():
    import os

    import tiktok_api as tt

    cfg = load_cfg()
    # Overrides desde el workflow manual (Run workflow → modo / privacidad)
    if os.environ.get("PUBLISH_MODE") in ("draft", "direct"):
        cfg["publish"]["mode"] = os.environ["PUBLISH_MODE"]
    if os.environ.get("PRIVACY_LEVEL"):
        cfg["publish"]["privacy_level"] = os.environ["PRIVACY_LEVEL"]
    cmd_ideas()
    q = load_queue()
    todo = pending(q)[: cfg["publish"]["videos_per_run"]]
    if not todo:
        print("📭 Cola vacía. Agrega ideas en content/queue.yaml o configura ANTHROPIC_API_KEY.")
        return
    token = tt.refresh_access_token()
    posted = json.loads(POSTED.read_text())
    mode = cfg["publish"]["mode"]
    for it in todo:
        path = OUT / f"{it['id']}.mp4"
        if not path.exists():
            render(it, cfg, path)
        cap = caption_for(it, cfg)
        print(f"🚀 Subiendo {it['id']} ({mode})…")
        try:
            pid = tt.upload(token, path, cap, cfg["publish"])
            st = tt.wait_status(token, pid)
            ok = st.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "PROCESSING_UPLOAD")
            it["status"] = ("published" if mode == "direct" else "uploaded") if ok else "failed"
            posted.append({
                "id": it["id"], "publish_id": pid, "mode": mode, "status": st.get("status"),
                "fail_reason": st.get("fail_reason"),
                "post_ids": st.get("publicaly_available_post_id") or st.get("publicly_available_post_id"),
                "caption": cap, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            print(f"   ✅ {it['status']}")
        except tt.TikTokError as e:
            it["status"] = "failed"
            it["error"] = str(e)
            print(f"   ❌ {e}")
    save_queue(q)
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=2) + "\n")
    if any(i["status"] == "failed" for i in todo):
        sys.exit(1)


def cmd_skip(item_id):
    q = load_queue()
    for i in q:
        if i["id"] == item_id:
            i["status"] = "skip"
    save_queue(q)


if __name__ == "__main__":
    args = sys.argv[1:] or ["list"]
    cmd, rest = args[0], args[1:]
    {
        "list": lambda: cmd_list(),
        "render": lambda: cmd_render(*(rest or ["next"])),
        "ideas": lambda: cmd_ideas(force="--force" in rest),
        "publish": lambda: cmd_publish(),
        "skip": lambda: cmd_skip(rest[0]),
    }.get(cmd, lambda: print(__doc__))()
