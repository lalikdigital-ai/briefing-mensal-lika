# -*- coding: utf-8 -*-
import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".")
CORS(app)

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY")
NOTION_TOKEN       = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = "99729d87e9884edd8b57dfc5dffc842d"  # Notion novo - Leoa Business

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Lika Briefing Mensal - online"})


@app.route("/briefing", methods=["GET"])
def serve_form():
    return send_from_directory(".", "briefing.html")


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.form.get("dados")
        if not raw:
            return jsonify({"error": "Campo 'dados' ausente"}), 400
        dados = json.loads(raw)
    except Exception as e:
        return jsonify({"error": f"JSON invalido: {str(e)}"}), 400

    nome    = dados.get("nome", "Cliente")
    hoje    = datetime.now().strftime("%d/%m/%Y")
    hoje_iso = datetime.now().strftime("%Y-%m-%d")

    diagnostico = gerar_diagnostico(dados)

    try:
        criar_pagina_notion(nome, hoje, hoje_iso, dados, diagnostico)
    except Exception as e:
        app.logger.error(f"Erro Notion: {str(e)}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok"}), 200


def gerar_diagnostico(dados):
    prompt = f"""Voce e a Lika Santana, estrategista de conteudo para profissionais de Saude & Beauty.
Com base no briefing abaixo, gere um diagnostico estrategico em portugues para orientar a producao de conteudo do proximo mes.

BRIEFING:
{json.dumps(dados, ensure_ascii=False, indent=2)}

Estruture em 5 secoes:
1. Visao Geral do Mes
2. Oportunidades de Conteudo
3. Procedimentos e Servicos em Destaque
4. Historias que Podem Virar Conteudo
5. Direcao Estrategica para o Proximo Mes

Tom: direto, estrategico, sem jargao. Maximo 400 palavras."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
                "temperature": 0.7
            },
            timeout=30
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Erro ao gerar diagnostico: {str(e)}"


def criar_pagina_notion(nome, hoje, hoje_iso, dados, diagnostico):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
        "Notion-Version": "2022-06-28"
    }

    def h2(texto):
        return {"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": texto}}]}}

    def callout(emoji, titulo, conteudo):
        texto = f"{titulo}\n{conteudo or 'Nao informado'}"
        return {"object": "block", "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": texto}}],
                    "icon": {"type": "emoji", "emoji": emoji},
                    "color": "gray_background"
                }}

    def paragrafo(texto):
        return {"object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": texto or "Nao informado"}}]}}

    def divider():
        return {"object": "block", "type": "divider", "divider": {}}

    materiais_str = ", ".join(dados.get("materiais", [])) or "Nao informado"
    links_str     = "\n".join(dados.get("referencias_links", [])) or "Nenhum"

    blocos = [
        h2("Dados e Disponibilidade"),
        callout("📅", "Mes de referencia:", dados.get("mes", "")),
        callout("🎬", "Consegue gravar?", dados.get("gravacao", "")),
        callout("📦", "Materiais disponiveis:", materiais_str),
        callout("🗓️", "Preferencia de data:", dados.get("preferencia_datas", "") + " " + dados.get("datas_preferidas", "")),
        callout("📝", "Obs. gravacao:", dados.get("obs_gravacao", "") or "Nenhuma"),
        divider(),
        h2("O que esta acontecendo no negocio"),
        callout("🚧", "Principais objecoes:", dados.get("objecoes", "")),
        callout("❌", "Motivo dos nao-fechamentos:", dados.get("nao_fechamentos", "")),
        callout("⭐", "Destaque do mes:", dados.get("destaque_atendimento", "")),
        divider(),
        h2("Historias e conteudo do mes"),
        callout("💬", "Situacoes marcantes:", dados.get("situacoes_marcantes", "")),
        callout("🏆", "Resultados de pacientes:", dados.get("resultados_pacientes", "")),
        callout("💉", "Procedimentos em destaque:", dados.get("servicos_destaque", "")),
        callout("🚀", "Novidades:", dados.get("novidades", "")),
        callout("📌", "Temas para conteudo:", dados.get("temas_conteudo", "")),
        callout("🔗", "Referencias:", links_str),
        callout("📣", "Observacoes extras:", dados.get("observacoes_extras", "")),
        divider(),
        h2("Diagnostico Estrategico IA"),
        paragrafo(diagnostico),
    ]

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Briefing": {"title": [{"text": {"content": f"Briefing {nome} - {hoje}"}}]},
            "Dia Recebido": {"date": {"start": hoje_iso}},
            "Status": {"select": {"name": "Não usado"}}
        },
        "children": blocos
    }

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=30
    )

    if not r.ok:
        app.logger.error(f"Notion error {r.status_code}: {r.text}")
        r.raise_for_status()

    return r.json()


if __name__ == "__main__":
    app.run(debug=True)
