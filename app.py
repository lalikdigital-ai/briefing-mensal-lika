import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".")

GROQ_API_KEY         = os.environ.get("GROQ_API_KEY")
NOTION_TOKEN         = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID   = os.environ.get("NOTION_DATABASE_ID")  # 0faf53c2-3c43-483a-9305-9a3e8f204292


# ──────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Lika Briefing Mensal — online"})


@app.route("/briefing", methods=["GET"])
def serve_form():
    return send_from_directory(".", "briefing.html")


# ──────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.form.get("dados")
        if not raw:
            return jsonify({"error": "Campo 'dados' ausente"}), 400
        dados = json.loads(raw)
    except Exception as e:
        return jsonify({"error": f"JSON inválido: {str(e)}"}), 400

    nome = dados.get("nome", "Cliente")
    hoje = datetime.now().strftime("%d/%m/%Y")
    hoje_iso = datetime.now().strftime("%Y-%m-%d")

    diagnostico = gerar_diagnostico(dados)
    criar_pagina_notion(nome, hoje, hoje_iso, dados, diagnostico)

    return jsonify({"status": "ok"}), 200


# ──────────────────────────────────────────────
def gerar_diagnostico(dados: dict) -> str:
    prompt = f"""
Você é a Lika Santana, estrategista de conteúdo especializada em profissionais de Saúde & Beauty.
Com base no briefing mensal abaixo, gere um diagnóstico estratégico em português para orientar
a produção de conteúdo do próximo mês.

BRIEFING:
{json.dumps(dados, ensure_ascii=False, indent=2)}

Estruture o diagnóstico em exatamente 5 seções:
1. Visão Geral do Mês
2. Oportunidades de Conteúdo (baseadas nas objeções e no que está acontecendo no negócio)
3. Procedimentos e Serviços em Destaque
4. Histórias que Podem Virar Conteúdo
5. Direção Estratégica para o Próximo Mês

Tom: direto, estratégico, sem jargão de marketing. Escreva como briefing interno para a equipe.
Máximo 400 palavras no total.
"""
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
        return f"Erro ao gerar diagnóstico: {str(e)}"


# ──────────────────────────────────────────────
def criar_pagina_notion(nome, hoje, hoje_iso, dados, diagnostico):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    def bloco_h2(texto):
        return {"object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": texto}}]}}

    def bloco_callout(emoji, titulo, conteudo):
        return {"object": "block", "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": f"{titulo}\n{conteudo or 'Não informado'}"}}],
                    "icon": {"type": "emoji", "emoji": emoji},
                    "color": "gray_background"
                }}

    def bloco_paragrafo(texto):
        return {"object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": texto or "Não informado"}}]}}

    def divider():
        return {"object": "block", "type": "divider", "divider": {}}

    materiais_str = ", ".join(dados.get("materiais", [])) or "Não informado"
    links_str     = "\n".join(dados.get("referencias_links", [])) or "Nenhum"

    blocos = [
        bloco_h2("📋 Dados e Disponibilidade"),
        bloco_callout("📅", "Mês de referência:", dados.get("mes", "")),
        bloco_callout("🎬", "Consegue gravar?", dados.get("gravacao", "")),
        bloco_callout("📦", "Materiais disponíveis:", materiais_str),
        bloco_callout("🗓️", "Preferência de data:", dados.get("preferencia_datas", "") + " " + dados.get("datas_preferidas", "")),
        bloco_callout("📝", "Obs. sobre gravação:", dados.get("obs_gravacao", "") or "Nenhuma"),
        divider(),
        bloco_h2("💼 O que está acontecendo no negócio"),
        bloco_callout("🚧", "Principais objeções:", dados.get("objecoes", "")),
        bloco_callout("❌", "Motivo dos não-fechamentos:", dados.get("nao_fechamentos", "")),
        bloco_callout("⭐", "Atendimento/resultado em destaque:", dados.get("destaque_atendimento", "")),
        divider(),
        bloco_h2("✨ Histórias e conteúdo do mês"),
        bloco_callout("💬", "Situações marcantes:", dados.get("situacoes_marcantes", "")),
        bloco_callout("🏆", "Resultados de pacientes:", dados.get("resultados_pacientes", "")),
        bloco_callout("💉", "Procedimentos/serviços em destaque:", dados.get("servicos_destaque", "")),
        bloco_callout("🚀", "Novidades:", dados.get("novidades", "")),
        bloco_callout("📌", "Temas para o conteúdo:", dados.get("temas_conteudo", "")),
        bloco_callout("🔗", "Referências/links:", links_str),
        bloco_callout("📣", "Observações extras:", dados.get("observacoes_extras", "")),
        divider(),
        bloco_h2("🧠 Diagnóstico Estratégico (IA)"),
        bloco_paragrafo(diagnostico),
    ]

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Briefing": {"title": [{"text": {"content": f"Briefing {nome} — {hoje}"}}]},
            "Dia Recebido": {"date": {"start": hoje_iso}},
            "Status": {"select": {"name": "Não usado"}}
        },
        "children": blocos
    }

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload,
        timeout=30
    )
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    app.run(debug=True)
