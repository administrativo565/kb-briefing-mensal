"""
KB Briefing Mensal - Servidor de Automacao v8
Recebe briefing do cliente -> Gera diagnostico IA -> Salva no Notion
Notion: titulo com nome + data, propriedades simples (Dia Recebido + Status),
conteudo completo do briefing + diagnostico IA como blocos da pagina.
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

IMPORTANTE: A KB Company e a AGENCIA que presta servico. O diagnostico deve falar sobre o NEGOCIO DO CLIENTE, usando o nome do cliente fornecido no campo nomeCliente, nao sobre a KB Company.

Estruture o diagnostico nas seguintes secoes:
1. VISAO GERAL DO MES
2. ANALISE DE PERFORMANCE COMERCIAL
3. PONTOS FORTES
4. DESAFIOS E OPORTUNIDADES
5. RECOMENDACOES ESTRATEGICAS DE CONTEUDO
6. PROXIMOS PASSOS PRIORITARIOS

Responda sempre em portugues. Seja especifico, pratico e actionavel."""


# ── Blocos Notion ─────────────────────────────────────────────────────────────

def rt(texto):
    """Rich text simples, max 2000 chars."""
    return [{"type": "text", "text": {"content": str(texto)[:2000]}}]


def heading2(texto):
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": rt(texto)}}


def heading3(texto):
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": rt(texto)}}


def paragrafo(texto, bold=False):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text",
                                         "text": {"content": str(texto)[:2000]},
                                         "annotations": {"bold": bold}}]}}


def callout(texto, icon="📋"):
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": rt(str(texto)[:2000]),
                        "icon": {"type": "emoji", "emoji": icon},
                        "color": "gray_background"}}


def divider():
    return {"object": "block", "type": "divider", "divider": {}}


def linha(label, valor):
    """Retorna um bloco paragrafo 'Label: valor' se valor existir."""
    if not valor or str(valor).strip() in ("", "0", "—"):
        return None
    return paragrafo(f"{label}: {valor}")


# ── Monta blocos com todos os dados do briefing ───────────────────────────────

def blocos_briefing(d):
    """Transforma os dados do formulario em blocos Notion organizados."""
    blocos = []

    # ── IDENTIFICAÇÃO ──────────────────────────────────────────────────────────
    blocos.append(heading2("🖤  BRIEFING DO CLIENTE"))
    blocos.append(divider())

    id_items = []
    if d.get("nomeCliente"):   id_items.append(f"👤 Cliente: {d['nomeCliente']}")
    if d.get("mesReferencia"): id_items.append(f"📅 Mês de referência: {d['mesReferencia']}")
    if d.get("dataEnvio"):     id_items.append(f"🕐 Preenchido em: {d['dataEnvio']}")
    if id_items:
        blocos.append(callout("\n".join(id_items), "🖤"))

    # ── DISPONIBILIDADE PARA GRAVAÇÃO ──────────────────────────────────────────
    blocos.append(heading3("📹  Disponibilidade para Gravação"))

    grav_items = []
    if d.get("podeGravar"):            grav_items.append(f"Pode gravar: {d['podeGravar']}")
    if d.get("materiaisDisponiveis"):  grav_items.append(f"Materiais disponíveis: {d['materiaisDisponiveis']}")
    if d.get("preferenciaData0515"):   grav_items.append(f"Preferência de data (05-15): {d['preferenciaData0515']}")
    if d.get("obsGravacao"):           grav_items.append(f"Observações: {d['obsGravacao']}")

    if grav_items:
        blocos.append(callout("\n".join(grav_items), "📹"))
    else:
        blocos.append(callout("Sem informações de gravação preenchidas.", "📹"))

    # ── DADOS COMERCIAIS ───────────────────────────────────────────────────────
    blocos.append(divider())
    blocos.append(heading3("💰  Dados Comerciais"))

    com_items = []
    if d.get("funisUtilizados"):       com_items.append(f"Funis utilizados: {d['funisUtilizados']}")
    if d.get("funilMaisResultado"):    com_items.append(f"Funil com mais resultado: {d['funilMaisResultado']}")
    if d.get("callsAgendadas"):        com_items.append(f"Calls agendadas: {d['callsAgendadas']}")
    if d.get("vendasFechadas"):        com_items.append(f"Vendas fechadas: {d['vendasFechadas']}")
    if d.get("ticketMedio"):           com_items.append(f"Ticket médio: R$ {d['ticketMedio']}")
    if d.get("taxaConversao"):         com_items.append(f"Taxa de conversão: {d['taxaConversao']}")

    if com_items:
        blocos.append(callout("\n".join(com_items), "💰"))

    if d.get("objecoesRecorrentes"):
        blocos.append(paragrafo("Principais objeções:", bold=True))
        blocos.append(callout(d["objecoesRecorrentes"], "🚫"))

    if d.get("motivoNaoFechamento"):
        blocos.append(paragrafo("Motivo dos não-fechamentos:", bold=True))
        blocos.append(callout(d["motivoNaoFechamento"], "❓"))

    if d.get("destaqueDoMes"):
        blocos.append(paragrafo("Destaque do mês:", bold=True))
        blocos.append(callout(d["destaqueDoMes"], "⭐"))

    # ── HISTÓRIAS & CONTEÚDO ───────────────────────────────────────────────────
    blocos.append(divider())
    blocos.append(heading3("✍️  Histórias & Conteúdo do Mês"))

    if d.get("historiasDoMes"):
        blocos.append(paragrafo("Histórias do mês:", bold=True))
        blocos.append(callout(d["historiasDoMes"], "💬"))

    if d.get("resultadosClientes"):
        blocos.append(paragrafo("Resultados de clientes:", bold=True))
        blocos.append(callout(d["resultadosClientes"], "🏆"))

    if d.get("produtosServicos"):
        blocos.append(paragrafo("Produtos / serviços em destaque:", bold=True))
        blocos.append(callout(d["produtosServicos"], "💎"))

    if d.get("novidades"):
        blocos.append(paragrafo("Novidades / lançamentos:", bold=True))
        blocos.append(callout(d["novidades"], "🚀"))

    if d.get("temasEspecificos"):
        blocos.append(paragrafo("Temas específicos para o conteúdo:", bold=True))
        blocos.append(callout(d["temasEspecificos"], "🎯"))

    if d.get("referencias"):
        blocos.append(paragrafo("Referências de conteúdo:", bold=True))
        blocos.append(callout(d["referencias"], "🔗"))

    if d.get("obsFinais"):
        blocos.append(paragrafo("Observações finais:", bold=True))
        blocos.append(callout(d["obsFinais"], "📝"))

    # ── Separador antes do diagnóstico ────────────────────────────────────────
    blocos.append(divider())
    blocos.append(heading2("🧠  DIAGNÓSTICO ESTRATÉGICO — IA"))
    blocos.append(divider())

    return blocos


def texto_para_blocos(texto):
    """Converte texto do Groq em blocos Notion."""
    blocos = []
    for linha_txt in texto.strip().split("\n"):
        linha_txt = linha_txt.strip()
        if not linha_txt:
            continue
        if re.match(r"^\d+\.\s+[A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚ ]+$", linha_txt):
            blocos.append(heading3(linha_txt))
        elif linha_txt.startswith("**") and linha_txt.endswith("**"):
            blocos.append(paragrafo(linha_txt.strip("*"), bold=True))
        elif linha_txt.startswith("#"):
            nivel = len(linha_txt) - len(linha_txt.lstrip("#"))
            texto_h = linha_txt.lstrip("#").strip()
            blocos.append(heading2(texto_h) if nivel <= 2 else heading3(texto_h))
        else:
            blocos.append(paragrafo(linha_txt))
    return blocos


# ── Groq ──────────────────────────────────────────────────────────────────────

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


# ── Notion ────────────────────────────────────────────────────────────────────

def salvar_no_notion(dados, diagnostico):
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return {"erro": "Notion nao configurado"}

    nome = dados.get("nomeCliente", "Cliente")
    hoje = datetime.now()
    data_fmt = hoje.strftime("%d/%m/%Y")
    titulo = f"Briefing {nome} — {data_fmt}"

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # Propriedades: apenas título + Dia Recebido + Status
    properties = {
        "Briefing": {"title": rt(titulo)},
        "Dia Recebido": {"date": {"start": hoje.strftime("%Y-%m-%d")}},
        "Status": {"select": {"name": "Não usado"}}
    }

    body = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
        "children": []
    }

    resp = req_lib.post("https://api.notion.com/v1/pages", headers=headers, json=body, timeout=30)
    if not resp.ok:
        return {"erro": resp.text}

    page_id = resp.json().get("id")

    # Monta todos os blocos: briefing completo + diagnóstico IA
    todos_blocos = blocos_briefing(dados) + texto_para_blocos(diagnostico)

    # Insere em lotes de 100 (limite da API Notion)
    for i in range(0, len(todos_blocos), 100):
        lote = todos_blocos[i:i + 100]
        req_lib.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers, json={"children": lote}, timeout=30
        )

    return {"ok": True, "page_id": page_id, "titulo": titulo}


# ── Rotas Flask ───────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        content_type = request.content_type or ""

        # O formulário envia FormData com campo 'dados' contendo JSON
        if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            dados_raw = request.form.get("dados", "")
            if dados_raw:
                dados = json.loads(dados_raw)
            else:
                dados = request.form.to_dict()
        elif "application/json" in content_type:
            dados = request.get_json(force=True) or {}
        else:
            # Tenta extrair de qualquer forma
            try:
                dados_raw = request.form.get("dados", "")
                dados = json.loads(dados_raw) if dados_raw else request.get_json(force=True) or {}
            except Exception:
                dados = {}

        if not dados:
            return jsonify({"erro": "Dados vazios"}), 400

        dados_str = json.dumps(dados, ensure_ascii=False, indent=2)
        diagnostico = chamar_groq(dados_str)
        resultado_notion = salvar_no_notion(dados, diagnostico)
        return jsonify({"ok": True, "notion": resultado_notion})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "KB Briefing Mensal v8 - online"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
