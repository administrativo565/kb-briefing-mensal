"""
KB Briefing Mensal - Servidor de Automacao v7
Dashboard visual com graficos e KPIs
"""
from flask import Flask, request, jsonify
import requests as req_lib
import json, os, re
from datetime import datetime

app = Flask(__name__)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")

PROMPT = """Voce e uma estrategista de conteudo digital que trabalha na agencia KB Company.
Sua tarefa e analisar o briefing mensal de um cliente e gerar um diagnostico estrategico detalhado.

IMPORTANTE: A KB Company e a AGENCIA que presta servico. O diagnostico deve falar sobre o NEGOCIO DO CLIENTE, usando o nome do cliente fornecido no campo cliente, nao sobre a KB Company.

Estruture o diagnostico nas seguintes secoes:
1. VISAO GERAL DO MES
2. ANALISE DE PERFORMANCE
3. PONTOS FORTES
4. DESAFIOS E OPORTUNIDADES
5. RECOMENDACOES ESTRATEGICAS
6. PROXIMOS PASSOS PRIORITARIOS

Responda sempre em portugues. Seja especifico e actionavel."""


def parse_numero(texto):
    """Tenta extrair um numero de um texto livre."""
    if not texto:
        return None
    t = texto.lower().strip()
    # Remove R$, espacos, pontos de milhar
    t = re.sub(r'r\$\s*', '', t)
    t = t.replace('.', '').replace(',', '.')
    multiplicador = 1
    if 'mil' in t or 'k' in t:
        multiplicador = 1000
        t = re.sub(r'[kmil]+', '', t)
    nums = re.findall(r'\d+(?:\.\d+)?', t)
    if nums:
        try:
            return float(nums[0]) * multiplicador
        except Exception:
            pass
    return None


def formatar_moeda(valor):
    if valor is None:
        return None
    if valor >= 1000:
        return f"R$ {valor:,.0f}".replace(',', '.')
    return f"R$ {valor:.0f}"


def chamar_groq(dados_str):
    if not GROQ_API_KEY:
        return "Erro: GROQ_API_KEY nao configurada."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"Dados do briefing:\n\n{dados_str}"}
        ],
        "max_tokens": 2000,
        "temperature": 0.7
    }
    try:
        resp = req_lib.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Erro ao chamar Groq: {str(e)}"


def rt(texto):
    return [{"type": "text", "text": {"content": str(texto)[:2000]}}]


def paragrafo(texto, bold=False):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": texto},
                                         "annotations": {"bold": bold}}]}}


def heading2(texto):
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": texto}}]}}


def heading3(texto):
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": texto}}]}}


def divider():
    return {"object": "block", "type": "divider", "divider": {}}


def callout(texto, icon="\U0001f5a4"):
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": [{"type": "text", "text": {"content": texto}}],
                        "icon": {"type": "emoji", "emoji": icon},
                        "color": "gray_background"}}


def blocos_formulario(dados):
    blocos = []
    blocos.append(heading2("\U0001f5a4 BRIEFING DO CLIENTE"))
    blocos.append(divider())

    pode_gravar = dados.get("podeGravar", "")
    if pode_gravar:
        blocos.append(heading3("Disponibilidade para Gravacao"))
        blocos.append(callout(pode_gravar))

    campos_comerciais = []
    for campo, label in [
        ("mes", "Mes"), ("faturamento", "Faturamento"),
        ("novosClientes", "Novos clientes"), ("servicoDestaque", "Servico destaque"),
        ("precoMedio", "Preco medio"), ("ticketMedio", "Ticket medio"),
        ("satisfacaoClientes", "Satisfacao"),
    ]:
        val = dados.get(campo, "")
        if val:
            campos_comerciais.append(f"{label}: {val}")

    if campos_comerciais:
        blocos.append(heading3("Dados Comerciais"))
        blocos.append(callout("\n".join(campos_comerciais)))

    campos_conteudo = [
        ("historias", "Historias"), ("temas", "Temas"), ("bastidores", "Bastidores"),
        ("duvidasFrequentes", "Duvidas"), ("tendencias", "Tendencias"),
        ("objetivoPrincipal", "Objetivo"), ("observacoes", "Observacoes"),
    ]
    tem_conteudo = any(dados.get(c, "") for c, _ in campos_conteudo)
    if tem_conteudo:
        blocos.append(heading3("Historias e Conteudo"))
        for campo, label in campos_conteudo:
            val = dados.get(campo, "")
            if val:
                blocos.append(callout(f"{label}: {val}"))

    blocos.append(divider())
    blocos.append(heading2("\U0001f5a4 DIAGNOSTICO ESTRATEGICO"))
    blocos.append(divider())
    return blocos


def texto_para_blocos(texto):
    blocos = []
    for linha in texto.strip().split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        if re.match(r"^\d+\.\s+[A-Z][A-Z ]+$", linha):
            blocos.append(heading3(linha))
        elif linha.startswith("**") and linha.endswith("**"):
            blocos.append(paragrafo(linha.strip("*"), bold=True))
        elif linha.startswith("#"):
            nivel = len(linha) - len(linha.lstrip("#"))
            texto_h = linha.lstrip("#").strip()
            blocos.append(heading2(texto_h) if nivel <= 2 else heading3(texto_h))
        else:
            blocos.append(paragrafo(linha))
    return blocos


def salvar_no_notion(dados, diagnostico):
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return {"erro": "Notion nao configurado"}

    cliente = dados.get("cliente", "Cliente")
    mes = dados.get("mes", datetime.now().strftime("%m/%Y"))
    titulo = f"Briefing {cliente} - {mes}"

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    properties = {"Cliente": {"title": rt(titulo)}}

    def add(prop, campo):
        val = dados.get(campo, "")
        if val:
            properties[prop] = {"rich_text": rt(val)}

    add("Mes", "mes")
    add("Disponibilidade", "podeGravar")
    add("Faturamento", "faturamento")
    add("Novos Clientes", "novosClientes")
    add("Servico Destaque", "servicoDestaque")
    add("Preco Medio", "precoMedio")
    add("Ticket Medio", "ticketMedio")
    add("Satisfacao", "satisfacaoClientes")
    add("Historias", "historias")
    add("Temas", "temas")
    add("Objetivo", "objetivoPrincipal")
    add("Observacoes", "observacoes")

    body = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
        "children": []
    }

    resp = req_lib.post("https://api.notion.com/v1/pages", headers=headers, json=body, timeout=30)
    if not resp.ok:
        return {"erro": resp.text}

    page_id = resp.json().get("id")
    todos_blocos = blocos_formulario(dados) + texto_para_blocos(diagnostico)
    for i in range(0, len(todos_blocos), 100):
        lote = todos_blocos[i:i+100]
        req_lib.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers, json={"children": lote}, timeout=30
        )

    return {"ok": True, "page_id": page_id, "titulo": titulo}


def prop_text(page, nome):
    try:
        items = page["properties"][nome]["rich_text"]
        return items[0]["text"]["content"] if items else ""
    except Exception:
        return ""


def build_dashboard_html(pages):
    # Extrair dados de todos os briefings para os graficos
    labels = []
    fat_vals = []
    cli_vals = []
    pode_sim = 0
    pode_nao = 0

    briefings = []
    for page in pages:
        titulo_prop = page["properties"].get("Cliente", {}).get("title", [])
        titulo = titulo_prop[0]["text"]["content"] if titulo_prop else "Sem titulo"
        # Extrair nome do cliente (antes do " - ")
        nome_cliente = titulo.split(" - ")[0].replace("Briefing ", "").strip()
        mes = prop_text(page, "Mes") or titulo.split(" - ")[-1] if " - " in titulo else ""
        created = page.get("created_time", "")[:10]
        page_url = page.get("url", "#")

        disponibilidade = prop_text(page, "Disponibilidade")
        faturamento_txt = prop_text(page, "Faturamento")
        novos_txt = prop_text(page, "Novos Clientes")
        servico = prop_text(page, "Servico Destaque")
        ticket_txt = prop_text(page, "Ticket Medio")
        preco_txt = prop_text(page, "Preco Medio")
        satisfacao_txt = prop_text(page, "Satisfacao")
        historias = prop_text(page, "Historias")
        temas_txt = prop_text(page, "Temas")
        objetivo = prop_text(page, "Objetivo")
        observacoes = prop_text(page, "Observacoes")

        fat_num = parse_numero(faturamento_txt)
        cli_num = parse_numero(novos_txt)
        ticket_num = parse_numero(ticket_txt)
        preco_num = parse_numero(preco_txt)
        sat_num = parse_numero(satisfacao_txt)

        # Para graficos
        labels.append(nome_cliente[:15])
        fat_vals.append(fat_num or 0)
        cli_vals.append(cli_num or 0)

        if disponibilidade:
            if "sim" in disponibilidade.lower() or "poder" in disponibilidade.lower():
                pode_sim += 1
            else:
                pode_nao += 1

        # Tags de temas
        temas_list = [t.strip() for t in re.split(r'[,;/\n]', temas_txt) if t.strip()] if temas_txt else []

        # Badge de disponibilidade
        if disponibilidade:
            if "sim" in disponibilidade.lower() or "poder" in disponibilidade.lower():
                grav_badge = '<span class="badge badge-green">&#10003; Vai gravar</span>'
            else:
                grav_badge = '<span class="badge badge-red">&#10007; Nao grava</span>'
        else:
            grav_badge = ''

        # Barra de satisfacao
        sat_bar = ""
        if sat_num and 0 < sat_num <= 10:
            pct = int(sat_num * 10)
            color = "#4ade80" if sat_num >= 7 else "#facc15" if sat_num >= 5 else "#f87171"
            sat_bar = (
                f'<div class="sat-wrap">'
                f'<div class="sat-bar"><div class="sat-fill" style="width:{pct}%;background:{color}"></div></div>'
                f'<span class="sat-num">{sat_num:.1f}/10</span>'
                f'</div>'
            )

        # KPI boxes
        def kpi(icon, label, valor, raw=None):
            display = valor if valor else (raw or "—")
            return (
                f'<div class="kpi">'
                f'<span class="kpi-icon">{icon}</span>'
                f'<span class="kpi-val">{display}</span>'
                f'<span class="kpi-label">{label}</span>'
                f'</div>'
            )

        kpis = (
            kpi("💰", "Faturamento", formatar_moeda(fat_num), faturamento_txt) +
            kpi("👥", "Novos Clientes", str(int(cli_num)) if cli_num else None, novos_txt) +
            kpi("🎯", "Ticket Médio", formatar_moeda(ticket_num), ticket_txt) +
            kpi("💎", "Serviço", None, servico[:20] + "..." if servico and len(servico) > 20 else servico)
        )

        # Tags de temas
        tags_html = "".join(f'<span class="tag">{t}</span>' for t in temas_list[:6]) if temas_list else ""

        # Objetivo
        obj_html = f'<div class="obj-box"><span class="obj-label">OBJETIVO</span><p class="obj-text">{objetivo}</p></div>' if objetivo else ""

        # Historias
        hist_html = f'<div class="hist-box"><span class="hist-label">HISTÓRIAS DO MÊS</span><p class="hist-text">{historias[:200]}{"..." if historias and len(historias) > 200 else ""}</p></div>' if historias else ""

        card = (
            f'<div class="card">'
            f'<div class="card-head">'
            f'<div class="card-head-left">'
            f'<span class="card-heart">\U0001f5a4</span>'
            f'<div>'
            f'<div class="card-name">{nome_cliente}</div>'
            f'<div class="card-meta">{mes} &nbsp;·&nbsp; {created}</div>'
            f'</div>'
            f'</div>'
            f'<div class="card-head-right">'
            f'{grav_badge}'
            f'<a class="btn-notion" href="{page_url}" target="_blank">Diagnóstico IA →</a>'
            f'</div>'
            f'</div>'
            f'<div class="kpi-row">{kpis}</div>'
            + (f'<div class="sat-section"><span class="sat-label">SATISFAÇÃO</span>{sat_bar}</div>' if sat_bar else '')
            + (f'<div class="content-row">{obj_html}{hist_html}</div>' if obj_html or hist_html else '')
            + (f'<div class="tags-row"><span class="tags-label">TEMAS</span><div class="tags">{tags_html}</div></div>' if tags_html else '')
            + f'</div>'
        )
        briefings.append(card)

    total = len(pages)
    plural = "s" if total != 1 else ""
    cards_html = "".join(briefings) if briefings else '<div class="empty"><span>\U0001f5a4</span>Nenhum briefing ainda.</div>'

    # JSON para Chart.js
    labels_json = json.dumps(labels, ensure_ascii=False)
    fat_json = json.dumps(fat_vals)
    cli_json = json.dumps(cli_vals)
    pode_json = json.dumps([pode_sim, pode_nao])

    tem_charts = any(v > 0 for v in fat_vals) or any(v > 0 for v in cli_vals)

    charts_section = ""
    if tem_charts and total > 0:
        charts_section = f"""
<div class="charts-section">
  <div class="charts-grid">
    <div class="chart-box">
      <div class="chart-title">Faturamento por Cliente (R$)</div>
      <canvas id="chartFat" height="180"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">Novos Clientes por Briefing</div>
      <canvas id="chartCli" height="180"></canvas>
    </div>
    <div class="chart-box chart-small">
      <div class="chart-title">Disponibilidade p/ Gravação</div>
      <canvas id="chartGrav" height="160"></canvas>
    </div>
  </div>
</div>
<script>
const LABELS = {labels_json};
const FAT   = {fat_json};
const CLI   = {cli_json};
const GRAV  = {pode_json};
const BAR_DEFAULTS = {{
  borderRadius: 6,
  borderSkipped: false,
}};
const TICK_COLOR = '#555';
const GRID_COLOR = '#1e1e1e';

Chart.defaults.color = TICK_COLOR;
Chart.defaults.font.family = 'Inter, sans-serif';

new Chart(document.getElementById('chartFat'), {{
  type: 'bar',
  data: {{
    labels: LABELS,
    datasets: [{{ label: 'Faturamento (R$)', data: FAT,
      backgroundColor: '#c8a96e33', borderColor: '#c8a96e',
      borderWidth: 1.5, ...BAR_DEFAULTS }}]
  }},
  options: {{
    responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: {{ color: GRID_COLOR }}, ticks: {{ color: TICK_COLOR }} }},
      y: {{ grid: {{ color: GRID_COLOR }}, ticks: {{ color: TICK_COLOR,
        callback: v => v >= 1000 ? 'R$' + (v/1000).toFixed(0) + 'k' : v }} }}
    }}
  }}
}});

new Chart(document.getElementById('chartCli'), {{
  type: 'bar',
  data: {{
    labels: LABELS,
    datasets: [{{ label: 'Novos Clientes', data: CLI,
      backgroundColor: '#818cf833', borderColor: '#818cf8',
      borderWidth: 1.5, ...BAR_DEFAULTS }}]
  }},
  options: {{
    responsive: true, plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: {{ color: GRID_COLOR }}, ticks: {{ color: TICK_COLOR }} }},
      y: {{ grid: {{ color: GRID_COLOR }}, ticks: {{ color: TICK_COLOR }} }}
    }}
  }}
}});

new Chart(document.getElementById('chartGrav'), {{
  type: 'doughnut',
  data: {{
    labels: ['Vai gravar', 'Nao grave'],
    datasets: [{{ data: GRAV,
      backgroundColor: ['#4ade8044', '#f8718044'],
      borderColor: ['#4ade80', '#f87180'],
      borderWidth: 1.5 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#666', padding: 16 }} }} }}
  }}
}});
</script>
"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>KB Company · Dashboard de Briefings</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0a0a0a;color:#f0ede8;font-family:Inter,sans-serif;font-weight:300;min-height:100vh;padding:0 24px 80px}}
  /* HEADER */
  .header{{max-width:1000px;margin:0 auto;padding:52px 0 40px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #1a1a1a}}
  .header-left .logo{{font-size:10px;font-weight:500;letter-spacing:.3em;text-transform:uppercase;color:#444;margin-bottom:10px}}
  .header-left h1{{font-size:clamp(22px,4vw,34px);font-weight:300;letter-spacing:-.02em;color:#f0ede8}}
  .header-right{{display:flex;align-items:center;gap:10px}}
  .count{{background:#141414;border:1px solid #252525;border-radius:20px;padding:6px 16px;font-size:13px;color:#555}}
  .refresh{{font-size:12px;color:#444;border:1px solid #2a2a2a;border-radius:20px;padding:6px 14px;background:#111;text-decoration:none;transition:all .2s}}
  .refresh:hover{{border-color:#c8a96e;color:#c8a96e}}
  /* CHARTS */
  .charts-section{{max-width:1000px;margin:36px auto 0}}
  .charts-grid{{display:grid;grid-template-columns:1fr 1fr auto;gap:16px;align-items:start}}
  .chart-box{{background:#111;border:1px solid #1c1c1c;border-radius:14px;padding:22px 22px 18px}}
  .chart-small{{min-width:220px}}
  .chart-title{{font-size:11px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:#555;margin-bottom:16px}}
  /* CARDS */
  .cards-section{{max-width:1000px;margin:28px auto 0;display:flex;flex-direction:column;gap:16px}}
  .section-label{{font-size:10px;font-weight:500;letter-spacing:.2em;text-transform:uppercase;color:#333;margin-bottom:4px}}
  .card{{background:#111;border:1px solid #1c1c1c;border-radius:16px;overflow:hidden;transition:border-color .2s}}
  .card:hover{{border-color:#2a2a2a}}
  /* CARD HEAD */
  .card-head{{display:flex;align-items:center;justify-content:space-between;padding:22px 26px 18px;border-bottom:1px solid #181818}}
  .card-head-left{{display:flex;align-items:center;gap:14px}}
  .card-heart{{font-size:20px;opacity:.4}}
  .card-name{{font-size:16px;font-weight:400;color:#e8e4de;margin-bottom:4px}}
  .card-meta{{font-size:12px;color:#444;letter-spacing:.04em}}
  .card-head-right{{display:flex;align-items:center;gap:10px;flex-shrink:0}}
  .badge{{font-size:11px;font-weight:500;padding:4px 10px;border-radius:20px;letter-spacing:.04em}}
  .badge-green{{background:#4ade8018;color:#4ade80;border:1px solid #4ade8040}}
  .badge-red{{background:#f8718018;color:#f87180;border:1px solid #f8718040}}
  .btn-notion{{font-size:12px;color:#555;text-decoration:none;border:1px solid #222;border-radius:8px;padding:6px 14px;transition:all .2s;white-space:nowrap}}
  .btn-notion:hover{{border-color:#c8a96e;color:#c8a96e}}
  /* KPI ROW */
  .kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #181818}}
  .kpi{{padding:16px 20px;border-right:1px solid #181818;display:flex;flex-direction:column;gap:4px}}
  .kpi:last-child{{border-right:none}}
  .kpi-icon{{font-size:16px;margin-bottom:2px}}
  .kpi-val{{font-size:17px;font-weight:500;color:#e8e4de;letter-spacing:-.01em}}
  .kpi-label{{font-size:10px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:#444}}
  /* SATISFACTION */
  .sat-section{{padding:14px 26px;border-bottom:1px solid #181818;display:flex;align-items:center;gap:16px}}
  .sat-label{{font-size:10px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:#444;min-width:90px}}
  .sat-wrap{{display:flex;align-items:center;gap:12px;flex:1}}
  .sat-bar{{flex:1;height:6px;background:#1e1e1e;border-radius:3px;overflow:hidden}}
  .sat-fill{{height:100%;border-radius:3px;transition:width .4s}}
  .sat-num{{font-size:13px;color:#888;white-space:nowrap}}
  /* CONTENT */
  .content-row{{display:grid;grid-template-columns:1fr 1fr;gap:0;border-bottom:1px solid #181818}}
  .obj-box,.hist-box{{padding:16px 26px}}
  .obj-box{{border-right:1px solid #181818}}
  .obj-label,.hist-label{{font-size:10px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:#444;display:block;margin-bottom:8px}}
  .obj-text{{font-size:13px;color:#c8c4be;line-height:1.5}}
  .hist-text{{font-size:13px;color:#888;line-height:1.5;font-style:italic}}
  /* TAGS */
  .tags-row{{padding:14px 26px;display:flex;align-items:center;gap:14px}}
  .tags-label{{font-size:10px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:#444;min-width:50px}}
  .tags{{display:flex;flex-wrap:wrap;gap:6px}}
  .tag{{background:#1a1a1a;border:1px solid #252525;border-radius:20px;padding:4px 12px;font-size:12px;color:#888}}
  /* EMPTY */
  .empty{{max-width:1000px;margin:100px auto;text-align:center;color:#333;font-size:15px}}
  .empty span{{display:block;font-size:52px;margin-bottom:18px;opacity:.2}}
  /* FOOTER */
  .footer{{max-width:1000px;margin:60px auto 0;text-align:center;font-size:11px;color:#222;letter-spacing:.15em;text-transform:uppercase}}
  @media(max-width:720px){{
    .charts-grid{{grid-template-columns:1fr}}
    .kpi-row{{grid-template-columns:1fr 1fr}}
    .content-row{{grid-template-columns:1fr}}
    .obj-box{{border-right:none;border-bottom:1px solid #181818}}
    .header{{flex-direction:column;gap:16px;text-align:center}}
  }}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <div class="logo">KB Company</div>
    <h1>Dashboard de Briefings</h1>
  </div>
  <div class="header-right">
    <span class="count">{total} briefing{plural}</span>
    <a class="refresh" href="/dashboard">↻ Atualizar</a>
  </div>
</div>
{charts_section}
<div class="cards-section">
  <div class="section-label" style="margin-top:8px">Respostas individuais</div>
  {cards_html}
</div>
<div class="footer">KB Company &copy; {datetime.now().year}</div>
</body>
</html>"""


@app.route("/dashboard", methods=["GET"])
def dashboard():
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return "<h1>Notion nao configurado</h1>", 500

    headers_notion = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    resp = req_lib.post(
        f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query",
        headers=headers_notion,
        json={"sorts": [{"timestamp": "created_time", "direction": "descending"}], "page_size": 50},
        timeout=30
    )
    if not resp.ok:
        return f"<h1>Erro: {resp.text}</h1>", 500

    pages = resp.json().get("results", [])
    return build_dashboard_html(pages)


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        content_type = request.content_type or ""
        if "application/json" in content_type:
            dados = request.get_json(force=True)
        else:
            dados = request.form.to_dict()

        if not dados:
            return jsonify({"erro": "Dados vazios"}), 400

        dados_str = json.dumps(dados, ensure_ascii=False, indent=2)
        diagnostico = chamar_groq(dados_str)
        resultado_notion = salvar_no_notion(dados, diagnostico)
        return jsonify({"ok": True, "diagnostico": diagnostico, "notion": resultado_notion})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "KB Briefing Mensal v7 - online"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
