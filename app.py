"""
KB Briefing Mensal - Servidor de Automacao v4
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


def callout(texto, icon="🖤"):
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": [{"type": "text", "text": {"content": texto}}],
                        "icon": {"type": "emoji", "emoji": icon},
                        "color": "gray_background"}}


def blocos_formulario(dados):
    blocos = []
    blocos.append(heading2("🖤 BRIEFING DO CLIENTE"))
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
    blocos.append(heading2("🖤 DIAGNOSTICO ESTRATEGICO"))
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
    return jsonify({"status": "KB Briefing Mensal v4 - online"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)