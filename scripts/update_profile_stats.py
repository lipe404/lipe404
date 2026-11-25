#!/usr/bin/env python3
"""Refresh the profile from the public GitHub REST API (no credentials)."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

OWNER = "lipe404"
ROOT = Path(__file__).resolve().parents[1]
START = "<!-- stats:start -->"
END = "<!-- stats:end -->"


def fetch_repos():
    results = []
    for page in range(1, 101):
        endpoint = (
            f"https://api.github.com/users/{OWNER}/repos"
            f"?type=owner&sort=full_name&direction=asc&per_page=100&page={page}"
        )
        request = Request(endpoint, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{OWNER}-profile-stats",
        })
        with urlopen(request, timeout=20) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("Resposta inesperada da API do GitHub")
        results.extend(batch)
        if len(batch) < 100:
            return results
    raise ValueError("Limite de paginação atingido, nada foi atualizado")


def summarize(repos, now):
    # The public endpoint plus these checks prevent publishing private repo data.
    owned = {
        r["id"]: r for r in repos
        if r.get("owner", {}).get("login", "").lower() == OWNER
        and r.get("private") is False and r.get("fork") is False
        and r.get("archived") is False and r["name"].lower() != OWNER
    }.values()
    if not owned:
        raise ValueError("A API não retornou projetos elegíveis; mantendo a versão anterior")
    languages = Counter(
        r["language"] for r in owned
        if isinstance(r.get("language"), str)
        and re.fullmatch(r"[\w .+#/\-]{1,40}", r["language"])
    )
    threshold = now - timedelta(days=90)
    recent = sum(
        threshold <= datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) <= now
        for r in owned if r.get("pushed_at")
    )
    top = sorted(languages.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    return len(owned), sum(r["stargazers_count"] for r in owned), recent, top


def graphic(top):
    shown = top[:6]
    height = 108 + 39 * max(len(shown), 1)
    colors = ("#7dd3fc", "#5eead4", "#c4b5fd", "#fde68a", "#f9a8d4", "#a5b4fc")
    rows = []
    for i, (name, count) in enumerate(shown):
        y = 93 + 39 * i
        width = round(276 * count / shown[0][1])
        rows.append(
            f'<text x="27" y="{y}" fill="#edf5fb" font-size="16">{escape(name)}</text>'
            f'<rect x="187" y="{y-13}" width="276" height="14" rx="7" fill="#25394a"/>'
            f'<rect x="187" y="{y-13}" width="{width}" height="14" rx="7" fill="{colors[i]}"/>'
            f'<text x="508" y="{y}" text-anchor="end" fill="#edf5fb" font-size="16">{count}</text>'
        )
    if not rows:
        rows.append('<text x="27" y="96" fill="#edf5fb" font-size="16">Sem classificação no GitHub</text>')
    description = "; ".join(f"{name}: {count}" for name, count in shown)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="536" height="{height}" viewBox="0 0 536 {height}" role="img" aria-labelledby="title desc">
<title id="title">Linguagens mais presentes</title>
<desc id="desc">{escape(description or "Sem classificação no GitHub")}</desc>
<rect x="1" y="1" width="534" height="{height-2}" rx="17" fill="#101c2b" stroke="#365068" stroke-width="2"/>
<g font-family="system-ui, -apple-system, sans-serif">
<text x="27" y="35" fill="#edf5fb" font-size="22" font-weight="700">Linguagens mais presentes</text>
<text x="27" y="59" fill="#b6cad9" font-size="14">Repositórios por linguagem principal</text>
{chr(10).join(rows)}
</g>
</svg>
'''


def update(repos, now):
    count, stars, recent, top = summarize(repos, now)
    readme = ROOT / "README.md"
    old = readme.read_text(encoding="utf-8")
    if old.count(START) != 1 or old.count(END) != 1:
        raise ValueError("Marcadores de estatísticas ausentes ou duplicados")
    intro, after_start = old.split(START)
    if END not in after_start:
        raise ValueError("Marcadores de estatísticas fora de ordem")
    _, outro = after_start.split(END)
    alt = "; ".join(f"{name}: {n}" for name, n in top[:6])
    block = f"""<!-- stats:start -->
| Repositórios públicos | Estrelas recebidas | Repositórios com push nos últimos 90 dias |
| ---: | ---: | ---: |
| {count} | {stars} | {recent} |

![Repositórios por linguagem principal. {alt or "Sem classificação no GitHub."}](assets/linguagens.svg)

<sub>Dados da API do GitHub, atualizados em {now:%d/%m/%Y}. Apenas repositórios públicos próprios, sem forks, arquivados ou este README. Cada projeto conta uma vez na sua linguagem principal.</sub>
<!-- stats:end -->"""
    (ROOT / "assets" / "linguagens.svg").write_text(graphic(top), encoding="utf-8")
    readme.write_text(intro + block + outro, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Use a local API response for verification")
    options = parser.parse_args()
    data = json.loads(options.fixture.read_text(encoding="utf-8")) if options.fixture else fetch_repos()
    update(data, datetime.now(timezone.utc))
