"""
KB Briefing Mensal - Servidor de Automacao v5
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
        ("mes", "Mes de referencia"),
        ("faturamento", "Faturamento"),
        ("novosClientes", "Novos clientes"),
        ("servicoDestaque", "Servico em destaque"),
        ("precoMedio", "Preco medio"),
        ("ticketMedio", "Ticket medio"),
        ("satisfacaoClientes", "Satisfacao dos clientes"),
    ]:
        val = dados.get(campo, "")
        if val:
            campos_comerciais.append(f"{label}: {val}")

    if campos_comerciais:
        blocos.append(heading3("Dados Comerciais"))
        blocos.append(callout("\n".join(campos_comerciais)))

    campos_conteudo = [
        ("historias", "Historias do mes"),
        ("temas", "Temas sugeridos"),
        ("bastidores", "Bastidores"),
        ("duvidasFrequentes", "Duvidas frequentes"),
        ("tendencias", "Tendencias do setor"),
        ("objetivoPrincipal", "Objetivo principal"),
        ("observacoes", "Observacoes"),
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

    body = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Cliente": {"title": [{"type": "text", "text": {"content": titulo}}]}
        },
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


def build_dashboard_html(pages):
    cards = ""
    for page in pages:
        props = page.get("properties", {})
        titulo_prop = props.get("Cliente", {}).get("title", [])
        titulo = titulo_prop[0]["text"]["content"] if titulo_prop else "Sem titulo"
        created = page.get("created_time", "")[:10]
        page_url = page.get("url", "#")
        cards += (
            '<a class="card" href="' + page_url + '" target="_blank">'
            '<div class="card-heart">\U0001f5a4</div>'
            '<div class="card-title">' + titulo + '</div>'
            '<div class="card-date">' + created + '</div>'
            '<div class="card-arrow">\u2192</div>'
            '</a>'
        )

    total = len(pages)
    plural = "s" if total != 1 else ""
    empty_block = "" if cards else '<div class="empty"><span>\U0001f5a4</span>Nenhum briefing encontrado ainda.</div>'

    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>KB Company \u00b7 Dashboard de Briefings</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet"/>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{background:#0a0a0a;color:#f0ede8;font-family:Inter,sans-serif;font-weight:300;min-height:100vh;padding:0 20px 80px}
  .header{max-width:860px;margin:0 auto;padding:64px 0 52px;text-align:center;border-bottom:1px solid #1e1e1e}
  .logo{font-size:11px;font-weight:500;letter-spacing:.3em;text-transform:uppercase;color:#444;margin-bottom:22px}
  h1{font-size:clamp(28px,5vw,48px);font-weight:300;letter-spacing:-.02em;color:#f0ede8;line-height:1.1}
  .sub{margin-top:14px;font-size:14px;color:#555;letter-spacing:.08em;text-transform:uppercase}
  .count{display:inline-block;margin-top:32px;background:#141414;border:1px solid #252525;border-radius:20px;padding:7px 18px;font-size:13px;color:#666}
  .refresh{display:inline-block;margin-left:10px;font-size:12px;color:#333;cursor:pointer;border:1px solid #2a2a2a;border-radius:20px;padding:7px 14px;background:#111;text-decoration:none;vertical-align:middle;transition:border-color .2s}
  .refresh:hover{border-color:#c8a96e;color:#c8a96e}
  .grid{max-width:860px;margin:52px auto 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px}
  .card{display:block;background:#111;border:1px solid #1c1c1c;border-radius:14px;padding:30px 26px;text-decoration:none;color:inherit;transition:border-color .2s,transform .15s;position:relative;overflow:hidden}
  .card:hover{border-color:#c8a96e;transform:translateY(-3px)}
  .card-heart{font-size:20px;margin-bottom:16px;opacity:.5}
  .card-title{font-size:15px;font-weight:400;color:#e8e4de;line-height:1.45;margin-bottom:10px}
  .card-date{font-size:12px;color:#444;letter-spacing:.06em}
  .card-arrow{position:absolute;right:22px;top:50%;transform:translateY(-50%);font-size:20px;color:#2a2a2a;transition:color .2s,right .15s}
  .card:hover .card-arrow{color:#c8a96e;right:18px}
  .empty{max-width:860px;margin:100px auto;text-align:center;color:#333;font-size:15px}
  .empty span{display:block;font-size:52px;margin-bottom:18px;opacity:.2}
  .footer{max-width:860px;margin:60px auto 0;text-align:center;font-size:12px;color:#2a2a2a;letter-spacing:.12em;text-transform:uppercase}
</style>
</head>
<body>
<div class="header">
  <div class="logo">KB Company</div>
  <h1>Dashboard de Briefings</h1>
  <div class="sub">Respostas mensais dos clientes</div>
  <div style="margin-top:28px">
    <span class="count">""" + str(total) + " briefing" + plural + " registrado" + plural + """</span>
    <a class="refresh" href="/dashboard">\u21bb atualizar</a>
  </div>
</div>
<div class="grid">""" + (cards if cards else empty_block) + """</div>
<div class="footer">KB Company &copy; """ + str(datetime.now().year) + """</div>
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
    return jsonify({"status": "KB Briefing Mensal v5 - online"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
