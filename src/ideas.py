"""Genera ideas nuevas para la cola con la API de Claude."""
from __future__ import annotations

import json
import os
import re

import requests


PROMPT = """Eres guionista de TikTok. Cuenta: {niche}.
Audiencia: {audience}. Idioma: {language}. Tono: {tone}.

Crea {n} ideas NUEVAS de videos cortos de texto animado (15–25 s).
No repitas estos temas ya usados: {used}

Responde SOLO con un arreglo JSON. Cada elemento:
{{"id": "slug-corto-unico", "hook": "gancho de máx 9 palabras que detenga el scroll",
"points": ["3 a 5 frases de máx 8 palabras cada una"],
"cta": "llamado a la acción de máx 5 palabras",
"caption": "descripción del post, 1 frase",
"hashtags": ["#2a3", "#especificos"]}}"""


def generate(cfg: dict, used_ids: list[str]) -> list[dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ℹ️  Sin ANTHROPIC_API_KEY: no se generan ideas nuevas.")
        return []
    ic = cfg["ideas"]
    prompt = PROMPT.format(
        niche=cfg["niche"], audience=cfg["audience"], language=cfg["language"],
        tone=cfg["tone"], n=ic["batch_size"], used=", ".join(used_ids[-60:]) or "ninguno",
    )
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": ic["model"], "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"])
    match = re.search(r"\[.*\]", text, re.S)
    ideas = json.loads(match.group(0)) if match else []
    clean = []
    for it in ideas:
        if not all(k in it for k in ("id", "hook", "points")) or it["id"] in used_ids:
            continue
        it["status"] = "pending"
        clean.append(it)
    print(f"💡 {len(clean)} ideas nuevas generadas")
    return clean
