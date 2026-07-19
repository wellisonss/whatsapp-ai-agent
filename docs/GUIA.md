# Guia Completo

Este documento explica **tudo o que o projeto faz** e **como adaptá-lo** à sua
empresa. É um template de chatbot de WhatsApp genérico: a base é robusta e
pronta para produção; os dados são apenas exemplos que você substitui.

---

## Sumário

1. [O que é](#1-o-que-é)
2. [Como funciona (o fluxo de uma mensagem)](#2-como-funciona-o-fluxo-de-uma-mensagem)
3. [Componentes, um a um](#3-componentes-um-a-um)
4. [O agente por dentro (LangGraph)](#4-o-agente-por-dentro-langgraph)
5. [RAG: base de conhecimento](#5-rag-base-de-conhecimento)
6. [Memória](#6-memória)
7. [Ferramentas (tools)](#7-ferramentas-tools)
8. [Fila, dedup e debounce](#8-fila-dedup-e-debounce)
9. [Configuração (todas as variáveis)](#9-configuração-todas-as-variáveis)
10. [Como rodar](#10-como-rodar)
11. [Como adaptar para a sua empresa](#11-como-adaptar-para-a-sua-empresa)
12. [Observabilidade e logs](#12-observabilidade-e-logs)
13. [Testes](#13-testes)
14. [Solução de problemas](#14-solução-de-problemas)
15. [Segurança](#15-segurança)

---

## 1. O que é

Um **assistente virtual que conversa pelo WhatsApp**. O usuário manda uma
mensagem em linguagem natural (ex.: *"qual foi o faturamento da loja Matriz nos
últimos 15 dias?"* ou *"quais são os horários de atendimento?"*) e o agente:

- entende a intenção,
- decide quais **ferramentas** usar (consultar uma API, buscar na base de
  conhecimento, normalizar datas...),
- responde com um texto formatado para o WhatsApp.

Ele foi desenhado para ser **adaptável a qualquer empresa**: você troca a
identidade do bot, a base de conhecimento e as ferramentas, e o resto continua
funcionando.

---

## 2. Como funciona (o fluxo de uma mensagem)

```
WhatsApp ─► WAHA ─► POST /webhook/waha
                         │
                         ├── valida o payload (pydantic)
                         ├── ignora mensagens próprias (fromMe) / vazias
                         ├── enqueue() no Redis Streams
                         │      ├── SET NX dedup:<message_id> (TTL 1h)
                         │      └── buffer de texto + chave de debounce
                         └── responde 200 ao WAHA (≤ 50ms)

(loop no worker)
Worker  ─► lê o stream (consumer group)
          ├── aguarda o debounce (2s sem novas msgs do mesmo chat)
          ├── drena o buffer (concatena mensagens em sequência numa só)
          ├── start_typing (mostra "digitando..." no WhatsApp)
          ├── run_agent(chat_id, texto)
          │     ├── load_memory: busca os fatos de longo prazo no Postgres
          │     ├── agent: o LLM (com tools) decide responder ou chamar tools
          │     ├── tools: executa as ferramentas pedidas
          │     └── format: limpa caracteres problemáticos para o WhatsApp
          ├── extract_facts → salva fatos novos na memória (best-effort)
          ├── send_chunked (envia a resposta, quebrando em partes de 1600 chars)
          └── stop_typing
```

**Por que separar webhook e worker?** O WAHA reenvia a mensagem se o webhook
demorar a responder — isso criaria um loop. Então o webhook só enfileira
(resposta instantânea) e todo o trabalho pesado (5–30s) acontece no worker.

---

## 3. Componentes, um a um

| Componente | Papel | Onde no código / compose |
|---|---|---|
| **API (FastAPI)** | Recebe webhooks e os enfileira; expõe healthchecks e admin. | `src/chatbot/main.py`, `api/` |
| **Worker** | Consome a fila, roda o agente, responde via WAHA. | `src/chatbot/workers/message_worker.py` |
| **Redis** | Fila (Streams) + dedup + debounce. | serviço `redis` |
| **Postgres + pgvector** | Sessão do LangGraph (checkpoint) + memória de longo prazo. | serviço `postgres` |
| **Qdrant** | Vector store da base de conhecimento (RAG híbrido). | serviço `qdrant` |
| **WAHA** | Gateway que conecta ao WhatsApp e dispara os webhooks. | serviço `waha` |
| **Langfuse** | Tracing/observabilidade (opcional). | externo, via `.env` |

---

## 4. O agente por dentro (LangGraph)

O agente é um **grafo de estados** (LangGraph). A topologia é:

```
[START] → load_memory → agent ⇄ tools → format → [END]
```

- **load_memory** — carrega os fatos de longo prazo do usuário (Postgres) e os
  injeta no system prompt.
- **agent** — chama o LLM (Gemini) com as tools disponíveis. O LLM ou responde
  direto, ou pede para chamar uma ou mais tools.
- **tools** — executa as tools solicitadas e devolve os resultados ao `agent`
  (o ciclo `agent ⇄ tools` se repete até o LLM ter o que precisa).
- **format** — pós-processa a resposta (troca glifos que o WhatsApp renderiza mal).

**Persistência de sessão:** cada conversa usa `thread_id = chat_id` no
checkpointer Postgres. Isso significa que o histórico é isolado por contato e
sobrevive a reinícios/redeploys — sem estado global mutável (que causaria
condições de corrida entre mensagens simultâneas de contatos diferentes).

**Controle de tokens:** só as últimas mensagens vão ao LLM a cada turno
(`_MAX_HISTORY_MESSAGES`), e históricos longos são resumidos automaticamente em
background (ver `agent/compaction.py`).

Arquivos: `agent/graph.py`, `agent/runner.py`, `agent/state.py`,
`agent/prompts.py`, `agent/llm.py`, `agent/compaction.py`.

---

## 5. RAG: base de conhecimento

Perguntas institucionais (história, políticas, produtos, unidades) são
respondidas com **RAG** (Retrieval-Augmented Generation):

1. Você coloca arquivos `.md` em `data/knowledge/`.
2. `make ingest` quebra cada documento **por cabeçalhos Markdown** e indexa no
   Qdrant (id determinístico por chunk → reindexar é idempotente).
3. Na conversa, a tool `retrieve_knowledge` faz **hybrid search** (densa +
   esparsa BM25) e, opcionalmente, um **rerank** (Cohere) para ordenar os melhores
   trechos, que são então entregues ao LLM.

- **Embeddings**: `rag/embeddings.py` (Gemini `gemini-embedding-001`).
- **Ingestão**: `rag/ingestion.py` + `scripts/ingest_kb.py`.
- **Recuperação**: `rag/retriever.py`.
- **Rerank**: `rag/reranker.py` (ligue com `RERANKER=cohere` + `COHERE_API_KEY`).

**Dica de escrita da base:** títulos claros e seções curtas dão chunks melhores.
Veja `data/knowledge/exemplo_base_conhecimento.md` como modelo.

---

## 6. Memória

São **duas camadas**, propositalmente separadas:

- **Sessão (curto prazo)** — o histórico vivo da conversa, mantido pelo
  checkpointer do LangGraph no Postgres. É resetável por `chat_id`.
- **Longo prazo** — *fatos estáveis* sobre o usuário (preferências, papel,
  tópicos que costuma consultar), extraídos automaticamente por um LLM ao final
  de cada turno e guardados em `user_facts` (Postgres). Sobrevive mesmo que a
  sessão seja limpa.

Por que separar? Injetar o histórico cru inteiro em todo prompt é caro, ruidoso
e vaza contexto antigo. A extração de fatos guarda só o que vale lembrar (JSON
estrito, até 5 fatos por turno, com fallback silencioso se algo falhar).

Arquivos: `memory/manager.py`, `memory/extractor.py`.

---

## 7. Ferramentas (tools)

As tools são funções que o LLM pode chamar. As que vêm no template:

| Tool | O que faz |
|---|---|
| `resolver_codigo_da_filial(filial)` | Converte um nome de unidade (mesmo com erro de digitação) no código oficial. |
| `get_dates(intervalo)` | Normaliza datas relativas (`hoje`, `ontem`, `ultimos_15_dias`...) para `dd/MM/yyyy`. |
| `buscar_faturamento_itens(...)` | **Exemplo** de tool que consulta uma API REST externa com filtros dinâmicos. |
| `retrieve_knowledge(query)` | Busca trechos na base de conhecimento (RAG). |

### Adicionando uma tool sua

```python
# src/chatbot/tools/minha_tool.py
from langchain_core.tools import tool

@tool
def minha_tool(parametro: str) -> str:
    """Descrição clara — o LLM lê isto para decidir quando usar a tool."""
    return f"resultado para {parametro}"
```

Depois registre em `src/chatbot/tools/__init__.py` (adicione a `ALL_TOOLS`) e
reinicie o worker. A qualidade da **docstring** importa muito: é o que o LLM usa
para decidir quando e como chamar a tool.

---

## 8. Fila, dedup e debounce

Implementados sobre **Redis Streams** (`infra/queue.py`):

- **Dedup** — cada `message_id` é registrado com `SET NX` e TTL de 1h. Se o WAHA
  reenviar a mesma mensagem, ela é ignorada.
- **Debounce** — quando o usuário manda várias mensagens em sequência, o worker
  espera ~2s sem novas mensagens e então **concatena tudo num único texto**,
  respondendo uma vez só (mais natural e mais barato).
- **Consumer group** — o stream usa ack/replay, então mensagens não se perdem se
  o worker cair no meio.

Ajuste a janela com `INBOX_DEBOUNCE_SECONDS`.

---

## 9. Configuração (todas as variáveis)

Tudo vem de uma única classe `Settings` (`core/config.py`), carregada do `.env`.

| Variável | Padrão | Descrição |
|---|---|---|
| `APP_ENV` | `local` | `local` / `staging` / `production`. Fora de produção, a resposta inclui um cabeçalho de contagem de tokens. |
| `APP_LOG_LEVEL` | `INFO` | Nível de log. |
| `BOT_NAME` | `Assistente` | Nome do bot no prompt. |
| `BOT_COMPANY` | `Sua Empresa` | Nome da empresa no prompt. |
| `BOT_DESCRIPTION` | `atendimento...` | O que o bot faz (entra no prompt). |
| `BOT_LANGUAGE` | `PT-BR` | Idioma das respostas. |
| `SYSTEM_PROMPT_FILE` | (vazio) | Caminho para um arquivo que substitui todo o system prompt. |
| `SALES_TOOL_ENABLED` | `true` | Liga/desliga a tool de exemplo de faturamento. |
| `GOOGLE_API_KEY` | — | Chave do Google Gemini (**obrigatória**). |
| `LLM_MODEL` | `gemini-2.5-flash` | Modelo do LLM. |
| `LLM_TEMPERATURE` | `0.2` | Criatividade do LLM. |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Modelo de embeddings do RAG. |
| `POSTGRES_*` | `chatbot` | Credenciais/host do Postgres. |
| `REDIS_URL` | `redis://redis:6379/0` | Conexão do Redis. |
| `INBOX_STREAM` / `INBOX_GROUP` | `chatbot:inbox` / `chatbot-workers` | Nomes do stream/grupo. |
| `INBOX_DEBOUNCE_SECONDS` | `2.0` | Janela de debounce. |
| `QDRANT_URL` / `QDRANT_COLLECTION` | `http://qdrant:6333` / `chatbot_kb` | Vector store. |
| `RERANKER` | `off` | `cohere` para ligar o rerank. |
| `COHERE_API_KEY` | (vazio) | Necessária se `RERANKER=cohere`. |
| `WAHA_BASE_URL` | `http://waha:3000` | URL interna do WAHA. |
| `WAHA_API_KEY` | — | Segredo do WAHA (**defina um forte**). |
| `WAHA_SESSION` | `default` | Nome da sessão do WhatsApp no WAHA. |
| `WAHA_DASHBOARD_PASSWORD` | `admin` | Senha do dashboard do WAHA. |
| `WEBHOOK_PUBLIC_URL` | `http://chatbot-api:8000/webhook/waha` | URL que o WAHA chama. |
| `ALLOWED_CHAT_IDS` | (vazio) | Lista de números permitidos. Vazio = todos. |
| `ERP_SALES_URL` | (exemplo) | Endpoint da API externa da tool de exemplo. |
| `ERP_SALES_MODE` | `vendas` | Parâmetro `mode` esperado pela sua API. |
| `LANGFUSE_ENABLED` | `false` | Liga o tracing. |
| `LANGFUSE_*` | — | Chaves/host do Langfuse. |

---

## 10. Como rodar

Pré-requisitos: **Docker** e **Docker Compose**.

```bash
cp .env.example .env       # ajuste no mínimo GOOGLE_API_KEY e WAHA_API_KEY
make up                    # sobe toda a stack
make ingest                # indexa a base de conhecimento no Qdrant
make logs                  # acompanha os logs
```

Conecte o WhatsApp: abra o dashboard do WAHA em <http://localhost:3002>
(`admin` / `WAHA_DASHBOARD_PASSWORD`), inicie a sessão `default` e escaneie o QR
code com o WhatsApp do número que será o bot.

Comandos úteis (`Makefile`): `make down`, `make build`, `make test`,
`make fmt`, `make lint`.

---

## 11. Como adaptar para a sua empresa

1. **Persona** — no `.env`: `BOT_NAME`, `BOT_COMPANY`, `BOT_DESCRIPTION`,
   `BOT_LANGUAGE`. Para reescrever o prompt inteiro (regras, tom, exemplos),
   crie um arquivo e aponte `SYSTEM_PROMPT_FILE` para ele.
2. **Base de conhecimento** — substitua os `.md` em `data/knowledge/` pelos seus
   e rode `make ingest`.
3. **Unidades/filiais** — edite o dicionário `LOJA_CODIGO_PARA_NOME` (e os
   apelidos/stopwords) em `src/chatbot/domain/stores.py`.
4. **Segmentos e canais** — edite as listas em `src/chatbot/domain/segments.py`.
5. **Integração com o seu sistema** — a tool de faturamento é um **exemplo** de
   como consultar uma API REST. Adapte `integrations/erp/sales_api.py` e
   `tools/sales.py` ao contrato da sua API, ou desligue com `SALES_TOOL_ENABLED=false`.
6. **Novas ferramentas** — veja a seção [Ferramentas](#7-ferramentas-tools).

Nada disso exige mexer no núcleo (grafo, fila, memória, RAG).

---

## 12. Observabilidade e logs

- **Logs estruturados** (structlog, JSON): `make logs`. Cada requisição carrega
  um `request_id` e o `chat_id` via `structlog.contextvars`.
- **Tracing** (opcional): `LANGFUSE_ENABLED=true` + chaves. Você vê cada passo do
  grafo, tokens, latência e custo por execução.

---

## 13. Testes

```bash
make test                                  # dentro do container
# ou, com Python local:
PYTHONPATH=src GOOGLE_API_KEY=test pytest tests
```

Os testes de `tests/unit` são puros (sem rede) e cobrem as regras de domínio
(datas, normalização de texto, resolução de filial, sugestão de segmentos). O
teste de integração faz um smoke do webhook.

---

## 14. Solução de problemas

- **O bot não responde** — confira `make logs`; veja se a sessão do WAHA está
  conectada (dashboard) e se `WEBHOOK_PUBLIC_URL` aponta para a API acessível
  pelo container do WAHA.
- **Erro de quota/429 do LLM** — o worker responde uma mensagem amigável e você
  vê o erro no log; reduza o volume ou troque de chave/modelo.
- **RAG não encontra nada** — rodou `make ingest` depois de editar a base? A
  coleção do Qdrant é `QDRANT_COLLECTION`.
- **Números indesejados falando com o bot** — restrinja com `ALLOWED_CHAT_IDS`.

---

## 15. Segurança

- **Nunca comite o seu `.env`** (já está no `.gitignore`). O `.env.example` só
  tem placeholders.
- Defina um `WAHA_API_KEY` forte e troque `WAHA_DASHBOARD_PASSWORD`.
- Trate os números de clientes como **dados pessoais**; use `ALLOWED_CHAT_IDS`
  em ambientes de teste para não responder a terceiros.
- Rotacione chaves de API se elas forem expostas.
