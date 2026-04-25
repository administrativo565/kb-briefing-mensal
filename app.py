"""
KB Briefing Mensal - Servidor de Automacao
Recebe o formulario -> chama Groq (Llama) -> salva no Notion
"""

from flask import Flask, request, jsonify
import requests as req_lib
import json
import os
from datetime import datetime

app = Flask(__name__)

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
NOTION_TOKEN       = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")

PROMPT = """Voce e uma estrategista de conteudo digital da KB Company.

Analise os dados do briefing mensal abaixo e gere um DIAGNOSTICO ESTRATEGICO COMPLETO em portugues.

DADOS DO BRIEFING:
{dados}

---

## VISAO GERAL DO MES
## PONTOS FORTES
## PONTOS DE ATENCAO
## DIAGNOSTICO COMERCIAL
## ESTRATEGIA DE CONTEUDO RECOMENDADA
## PROXIMOS PASSOS PRIORITARIOS

Seja especifico e responda sempre em portugues."""


def chamar_groq(dados_str):
    resp = req_lib.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": PROMPT.format(dados=dados_str)}], "temperature": 0.7, "max_tokens": 3000},
        timeout=60,
    )
    data = resp.json()
    if "choices" not in data:
        raise Exception(f"Groq error: {data}")
    return data["choices"][0]["message"]["content"]


def texto_para_blocos(texto):
    blocos = []
    for linha in texto.split("\n"):
        linha = linha.rstrip()
        if not linha:
            continue
        if linha.startswith("## "):
            blocos.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": linha[3:]}}]}})
        elif linha.startswith("# "):
            blocos.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": linha[2:]}}]}})
        else:
            while len(linha) > 1900:
                blocos.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": linha[:1900]}}]}})
                linha = linha[1900:]
            if linha:
                blocos.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": linha}}]}})
    return blocos


def salvar_no_notion(dados_str, diagnostico):
    try:
        dados = json.loads(dados_str) if isinstance(dados_str, str) else dados_str
        cliente = dados.get("nomeCliente") or dados.get("cliente") or "Cliente"
        mes = dados.get("mesReferencia") or dados.get("mes") or datetime.now().strftime("%Y-%m")
    except Exception:
        cliente = "Cliente"
        mes = datetime.now().strftime("%Y-%m")
    titulo = f"Diagnostico {cliente} - {mes}"
    blocos = texto_para_blocos(diagnostico)
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
    payload = {"parent": {"database_id": NOTION_DATABASE_ID}, "properties": {"Nome": {"title": [{"text": {"content": titulo}}]}}, "children": blocos[:100]}
    resp = req_lib.post("https://api.notion.com/v1/pages", headers=headers, json=payload, timeout=30)
    result = resp.json()
    if len(blocos) > 100 and result.get("id"):
        for i in range(100, len(blocos), 100):
            block_id = result.get("id")
            req_lib.patch(f"https://api.notion.com/v1/blocks/{block_id}/children", headers=headers, json={"children": blocos[i:i+100]}, timeout=30)
    return result


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "KB Briefing Mensal - servidor ativo"})


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        ct = request.content_type or ""
        if "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
            dados_str = request.form.get("dados", "")
        else:
            body = request.get_json(silent=True) or {}
            dados_str = body.get("dados", "")
        if not dados_str:
            return jsonify({"error": "Campo dados nao encontrado."}), 400
        diagnostico = chamar_groq(dados_str)
        notion_result = {}
        if NOTION_TOKEN and NOTION_DATABASE_ID:
            notion_result = salvar_no_notion(dados_str, diagnostico)
        return jsonify({"success": True, "diagnostico": diagnostico, "notion_page": notion_result.get("url", "")})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)