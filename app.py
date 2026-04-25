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
