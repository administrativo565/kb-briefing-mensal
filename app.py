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

PROMPT = """Voce e uma estrategista de conteudo digital que trabalha na agencia KB Company.
Abaixo estao os dados preenchidos pelo CLIENTE no briefing mensal.
O cliente e a pessoa ou negocio para quem a KB Company presta servicos de marketing e conteudo digital.

Gere um diagnostico estrategico COMPLETO sobre o CLIENTE com base nas informacoes abaixo.
O diagnostico deve falar sobre o NEGOCIO DO CLIENTE, usando o nome do cliente, nao sobre a KB Company.

DADOS DO CLIENTE:
{dados}

Estruture o diagnostico nas seguintes secoes:

1. VISAO GERAL DO MES - resumo do periodo com base nos dados fornecidos
2. PONTOS FORTES - o que esta funcionando bem no negocio do cliente
3. PONTOS DE ATENCAO - o que precisa de melhoria ou atencao
4. DIAGNOSTICO COMERCIAL - analise das metricas, funis e vendas
5. ESTRATEGIA DE CONTEUDO RECOMENDADA - sugestoes especificas para o proximo mes
6. PROXIMOS PASSOS PRIORITARIOS - acoes concretas e prioritarias

Responda sempre em portugues. Seja especifico e use os dados reais informados."""


def chamar_groq(dados_str):
    resp = req_lib.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": PROMPT.format(dados=dados_str)}],
            "temperature": 0.7,
            "max_tokens": 3000
        },
        timeout=60,
    )
    data = resp.json()
    if "choices" not in data:
        raise Exception(f"Groq error: {data}")
    return data["choices"][0]["message"]["content"]


def bloco_texto(texto, bold=False):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": str(texto)[:2000]}, "annotations": {"bold": bold}}]
        }
    }


def bloco_heading(texto, level=2):
    tipo = f"heading_{level}"
    return {
        "object": "block",
        "type": tipo,
        tipo: {"rich_text": [{"type": "text", "text": {"content": str(texto)}}]}
    }


def bloco_divider():
    return {"object": "block", "type": "divider", "divider": {}}


def campo(label, valor):
    if not valor:
        return []
    return [bloco_texto(f"{label}: {valor}")]


def blocos_formulario(dados):
    blocos = []
    blocos.append(bloco_heading("RESPOSTAS DO FORMULARIO", 2))
    blocos.append(bloco_divider())

    blocos.append(bloco_heading("DISPONIBILIDADE PARA GRAVACAO", 3))
    blocos += campo("Pode gravar", dados.get("podeGravar", ""))
    blocos += campo("Materiais disponiveis", dados.get("materiaisDisponiveis", ""))
    blocos += campo("Preferencia de data 05-15", dados.get("preferenciaData0515", ""))
    blocos += campo("Obs sobre gravacao", dados.get("obsGravacao", ""))

    blocos.append(bloco_divider())

    blocos.append(bloco_heading("DADOS COMERCIAIS", 3))
    blocos += campo("Funis utilizados", dados.get("funisUtilizados", ""))
    blocos += campo("Funil com mais resultado", dados.get("funilMaisResultado", ""))
    blocos += campo("Calls agendadas", dados.get("callsAgendadas", ""))
    blocos += campo("Vendas fechadas", dados.get("vendasFechadas", ""))
    blocos += campo("Ticket medio", dados.get("ticketMedio", ""))
    blocos += campo("Taxa de conversao", dados.get("taxaConversao", ""))
    blocos += campo("Objecoes recorrentes", dados.get("objecoesRecorrentes", ""))
    blocos += campo("Motivo nao-fechamento", dados.get("motivoNaoFechamento", ""))
    blocos += campo("Destaque do mes", dados.get("destaqueDoMes", ""))

    blocos.append(bloco_divider())

    blocos.append(bloco_heading("HISTORIAS E CONTEUDO", 3))
    blocos += campo("Historias do mes", dados.get("historiasDoMes", ""))
    blocos += campo("Resultados de clientes", dados.get("resultadosClientes", ""))
    blocos += campo("Produtos e servicos em destaque", dados.get("produtosServicos", ""))
    blocos += campo("Novidades e lancamentos", dados.get("novidades", ""))
    blocos += campo("Temas especificos", dados.get("temasEspecificos", ""))
    blocos += campo("Referencias de conteudo", dados.get("referencias", ""))
    blocos += campo("Tem audio", dados.get("temAudio", ""))
    blocos += campo("Obs finais", dados.get("obsFinais", ""))

    blocos.append(bloco_divider())
    blocos.append(bloco_heading("DIAGNOSTICO ESTRATEGICO GERADO POR IA", 2))
    blocos.append(bloco_divider())

    return blocos


def texto_para_blocos(texto):
    blocos = []
    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        blocos.append(bloco_texto(linha))
    return blocos


def salvar_no_notion(dados, diagnostico):
    cliente = dados.get("nomeCliente", dados.get("cliente", "Cliente"))
    mes = dados.get("mesReferencia", dados.get("mes", ""))
    if not mes:
        mes = datetime.now().strftime("%Y-%m")
    titulo = f"Briefing {cliente} - {mes}"

    blocos_form = blocos_formulario(dados)
    blocos_diag = texto_para_blocos(diagnostico)
    todos_blocos = blocos_form + blocos_diag

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Cliente": {"title": [{"text": {"content": titulo}}]}
        },
        "children": todos_blocos[:100]
    }
    resp = req_lib.post("https://api.notion.com/v1/pages", headers=headers, json=payload, timeout=30)
    result = resp.json()
    if len(todos_blocos) > 100 and result.get("id"):
        block_id = result.get("id")
        for i in range(100, len(todos_blocos), 100):
            req_lib.patch(
                f"https://api.notion.com/v1/blocks/{block_id}/children",
                headers=headers,
                json={"children": todos_blocos[i:i+100]},
                timeout=30
            )
    return result


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "KB Briefing Mensal - servidor ativo", "versao": "3.0"})


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        if request.content_type and "application/json" in request.content_type:
            body = request.get_json(force=True)
            dados_raw = body.get("dados", body)
        else:
            dados_str_raw = request.form.get("dados", "{}")
            dados_raw = json.loads(dados_str_raw)

        if isinstance(dados_raw, str):
            dados = json.loads(dados_raw)
        else:
            dados = dados_raw

        dados_str = "\n".join([f"{k}: {v}" for k, v in dados.items() if v])
        diagnostico = chamar_groq(dados_str)
        notion_result = salvar_no_notion(dados, diagnostico)

        return jsonify({
            "success": True,
            "diagnostico": diagnostico,
            "notion_page": notion_result.get("url", "")
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=False)
