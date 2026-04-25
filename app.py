"""
KB Briefing Mensal — Servidor de Automação
Recebe o formulário → chama Gemini → salva no Notion
"""

from flask import Flask, request, jsonify
import google.generativeai as genai
import requests
import json
import os
from datetime import datetime

app = Flask(__name__)

# ── Configurações (via variáveis de ambiente no Render) ──────────────────────────────────────
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
NOTION_TOKEN       = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")

genai.configure(api_key=GEMINI_API_KEY)

# ── Prompt do diagnóstico ────────────────────────────────────────────────────────────────────────────
PROMPT = """Você é uma estrategista de conteúdo digital da KB Company, especializada em diagnósticos mensais de performance para criadores de conteúdo e empreendedores digitais.

Analise os dados do briefing mensal abaixo e gere um DIAGNÓSTICO ESTRATÉGICO COMPLETO em português.

DADOS DO BRIEFING:
{dados}

---

Estruture seu diagnóstico exatamente assim:

## VISÃO GERAL DO MÊS
Resumo dos principais indicadores e contexto geral do mês.

## PONTOS FORTES
O que está funcionando bem e merece ser potencializado no próximo mês.

## PONTOS DE ATENÇÃO
Gargalos, oportunidades perdidas ou métricas abaixo do esperado.

## DIAGNÓSTICO COMERCIAL
Análise da taxa de conversão, objeções identificadas e performance de vendas. Use os números de calls, vendas e ticket médio informados.

## ESTRATÉGIA DE CONTEÚDO RECOMENDADA
Com base nas histórias do mês, resultados de clientes e produtos/serviços em destaque, sugira os ângulos de conteúdo mais estratégicos para o próximo mês.

## PRÓXIMOS PASSOS PRIORITÁRIOS
Liste as 3 a 5 ações mais importantes para o próximo mês, em ordem de prioridade.

Seja específico, estratégico e use os dados fornecidos para embasar cada análise. Responda sempre em português."""


# ── Funções auxiliares ───────────────────────────────────────────────────────────────────────────────────

def chamar_gemini(dados_str: str) -> str:
    """Chama a API do Gemini com os dados do briefing e retorna o diagnóstico."""
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(PROMPT.format(dados=dados_str))
    return response.text


def texto_para_blocos(texto: str) -> list:
    """Converte o texto do diagnóstico em blocos do Notion."""
    blocos = []
    for linha in texto.split("\n"):
        linha = linha.rstrip()
        if not linha:
            continue
        if linha.startswith("## "):
            blocos.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": linha[3:]}}]
                }
            })
        elif linha.startswith("# "):
            blocos.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": linha[2:]}}]
                }
            })
        else:
            while len(linha) > 1900:
                blocos.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": linha[:1900]}}]
                    }
                })
                linha = linha[1900:]
            if linha:
                blocos.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": linha}}]
                    }
                })
    return blocos


def salvar_no_notion(dados_str: str, diagnostico: str) -> dict:
    """Cria uma página no banco de dados do Notion com o diagnóstico."""

    try:
        dados = json.loads(dados_str) if isinstance(dados_str, str) else dados_str
        cliente = (
            dados.get("nomeCliente")
            or dados.get("cliente")
            or dados.get("nome_cliente")
            or "Cliente"
        )
        mes = (
            dados.get("mesReferencia")
            or dados.get("mes")
            or dados.get("mes_referencia")
            or datetime.now().strftime("%Y-%m")
        )
    except Exception:
        cliente = "Cliente"
        mes = datetime.now().strftime("%Y-%m")

    titulo = f"Diagnóstico {cliente} — {mes}"
    blocos  = texto_para_blocos(diagnostico)

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Nome": {
                "title": [{"text": {"content": titulo}}]
            }
        },
        "children": blocos[:100],
    }

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload,
        timeout=30,
    )
    result = resp.json()

    if len(blocos) > 100 and result.get("id"):
        page_id = result["id"]
        for i in range(100, len(blocos), 100):
            requests.patch(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=headers,
                json={"children": blocos[i : i + 100]},
                timeout=30,
            )

    return result


# ── Rotas ────────────────────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "✅ KB Briefing Mensal — servidor ativo"})


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
            return jsonify({"error": "Campo 'dados' não encontrado na requisição."}), 400

        print("📋 Briefing recebido — chamando Gemini...")
        diagnostico = chamar_gemini(dados_str)
        print(f"✅ Diagnóstico gerado ({len(diagnostico)} chars)")

        notion_result = {}
        if NOTION_TOKEN and NOTION_DATABASE_ID:
            notion_result = salvar_no_notion(dados_str, diagnostico)
            page_url = notion_result.get("url", "")
            print(f"📝 Salvo no Notion: {page_url}")
        else:
            print("⚠️  Notion não configurado — diagnóstico não salvo.")

        return jsonify({
            "success": True,
            "diagnostico": diagnostico,
            "notion_page": notion_result.get("url", ""),
        })

    except Exception as exc:
        print(f"❌ Erro: {exc}")
        return jsonify({"error": str(exc)}), 500


# ── Inicialização ────────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
