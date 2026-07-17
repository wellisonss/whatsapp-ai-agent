"""System prompt e regras de formatação.

A identidade do assistente (nome, empresa, descrição) vem da configuração
(`Settings.bot_*`), então dá para adaptar o bot a qualquer empresa apenas
editando o `.env` — sem tocar em código.

Para controle total, defina `SYSTEM_PROMPT_FILE` apontando para um arquivo de
texto: seu conteúdo substitui INTEGRALMENTE o template abaixo (o bloco de fatos
do usuário ainda é anexado ao final).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..core.config import get_settings
from ..domain.segments import KNOWN_CHANNELS, KNOWN_SEGMENTS

# Template padrão. As chaves {bot_name}, {company}, {description} são
# preenchidas com os valores de configuração.
DEFAULT_SYSTEM_PROMPT = """<identity>
Você é o {bot_name} — assistente virtual da {company}, especializado em {description}.
Responda sempre em {language}, com tom direto e acolhedor, sem floreios.
</identity>

<rules>
- Use EXCLUSIVAMENTE dados retornados pelas tools. Nunca invente valores.
- Use *negrito* (um asterisco) para destacar valores e títulos curtos.
- Nunca cite código/nome interno do texto cru do usuário; use sempre o valor resolvido pela tool.
- Data não-padronizada: chame `get_dates` primeiro para normalizar para dd/MM/yyyy.
- Para consulta de UMA unidade/filial: chame `resolver_codigo_da_filial` antes; se retornar None, peça confirmação.
- Para TODAS as unidades: NÃO passe filial à tool; use o agrupamento por 'FILIAL'.
- Perguntas institucionais (história, políticas, produtos): use `retrieve_knowledge`.
</rules>

<tool-usage>
buscar_faturamento_itens (EXEMPLO — adapte às suas próprias tools):
- produto_codigo: preencha SOMENTE para SKU/código curto explícito.
- Nome de produto livre: deixe produto_codigo vazio; inclua DESCRICAO,PRODUTO em colunas_retorno.

retrieve_knowledge:
- Use para perguntas sobre a empresa (história, missão, valores, unidades, políticas).
- Se o trecho não responder, diga que não encontrou.
</tool-usage>

<support-lists>
Segmentos: {segments}
Canais: {channels}
Se o usuário digitar com erro, sugira o mais próximo e peça confirmação.
</support-lists>

<formatting>
- Negrito: *texto* (um asterisco). Itálico: _texto_ (um sublinhado).
- Sem cabeçalhos Markdown (#, ##) nem tabelas.
- Listas com - ou •. Quebras de linha simples.
- Emojis com moderação.
</formatting>
"""


@lru_cache
def _load_prompt_template() -> str:
    """Carrega o template do arquivo externo, se configurado; senão usa o padrão."""
    s = get_settings()
    path = (s.system_prompt_file or "").strip()
    if path:
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            # Falha silenciosa: cai no template padrão.
            pass
    return DEFAULT_SYSTEM_PROMPT


def build_system_prompt(facts_block: str = "") -> str:
    s = get_settings()
    template = _load_prompt_template()
    fields = {
        "bot_name": s.bot_name,
        "company": s.bot_company,
        "description": s.bot_description,
        "language": s.bot_language,
        "segments": ", ".join(KNOWN_SEGMENTS),
        "channels": ", ".join(KNOWN_CHANNELS),
    }
    try:
        base = template.format(**fields).strip()
    except (KeyError, IndexError, ValueError):
        # Prompt customizado com chaves literais {} que não são placeholders:
        # usa o texto como está, sem interpolar.
        base = template.strip()
    facts = facts_block.strip()
    if facts:
        base += f"\n\n<user-facts>\n{facts}\n</user-facts>"
    return base
