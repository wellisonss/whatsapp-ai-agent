# WhatsApp AI Agent — template

Template **pronto para produção** de um agente conversacional de WhatsApp, feito
para ser adaptado a **qualquer empresa**. Você troca a identidade, a base de
conhecimento e as ferramentas — e tem um chatbot próprio no ar.

Construído com **LangGraph + RAG híbrido + memória em duas camadas + fila
assíncrona + observabilidade**, integrado ao WhatsApp via **WAHA**.

> 📖 Para a explicação completa de tudo que o projeto faz e como adaptá-lo,
> leia o **[Guia Completo](docs/GUIA.md)**.

## Visão geral

```
WhatsApp → WAHA → POST /webhook/waha (FastAPI)   ← só enfileira (resposta <50ms)
                            │
                            ▼
                   Redis Streams (dedup + debounce)
                            │
                            ▼
         Worker  ──►  LangGraph (checkpoint Postgres)
            │              │  ├─ tools: faturamento, filiais, datas (exemplo)
            │              │  └─ tool: retrieve_knowledge (Qdrant hybrid + rerank)
            │              ▼
            │         Memória de longo prazo (Postgres)
            ▼
         WAHA send (resposta WhatsApp)
                            │
                            ▼
                    Langfuse (tracing opcional)
```

## Recursos

- **Agente LangGraph** com fluxo `agent ⇄ tools` e persistência de sessão por `chat_id`.
- **RAG híbrido** (Qdrant): busca densa (Gemini) + esparsa (BM25) + rerank opcional (Cohere).
- **Memória em duas camadas**: sessão (checkpoint) + fatos de longo prazo (extraídos por LLM).
- **Compactação automática** de históricos longos para controlar tokens.
- **Fila resiliente** (Redis Streams) com dedup por `message_id` e debounce por chat.
- **Persona configurável** por `.env` — nome, empresa e descrição sem tocar em código.
- **Observabilidade**: logs estruturados (structlog) + tracing (Langfuse) opcional.
- **Docker Compose** com tudo: api, worker, Postgres+pgvector, Redis, Qdrant, WAHA.

## Como subir

```bash
cp .env.example .env       # ajuste GOOGLE_API_KEY, WAHA_API_KEY e a persona (BOT_*)
make up                    # sobe api, worker, postgres, redis, qdrant, waha
make ingest                # indexa data/knowledge no Qdrant
make logs                  # acompanha logs da api e worker
```

Depois, conecte o WhatsApp escaneando o QR no dashboard do WAHA em
<http://localhost:3002> (login: `admin` / `WAHA_DASHBOARD_PASSWORD`).

| Rota | Descrição |
|---|---|
| `POST /webhook/waha` | Recebe mensagens do WAHA (apenas enfileira) |
| `POST /admin/configure-webhook` | Reconfigura o webhook no WAHA |
| `GET /health`, `/health/deep` | Healthchecks |

## Adaptando para a sua empresa

Este projeto vem com **dados de exemplo**. Para torná-lo seu:

1. **Persona** → edite `BOT_NAME`, `BOT_COMPANY`, `BOT_DESCRIPTION` no `.env`.
   Para reescrever o prompt inteiro, aponte `SYSTEM_PROMPT_FILE` para um arquivo.
2. **Base de conhecimento** → substitua os `.md` em `data/knowledge/` e rode `make ingest`.
3. **Unidades/filiais** → edite `src/chatbot/domain/stores.py`.
4. **Segmentos/canais** → edite `src/chatbot/domain/segments.py`.
5. **Integração com o seu sistema** → adapte `src/chatbot/integrations/erp/sales_api.py`
   e a tool `src/chatbot/tools/sales.py` ao contrato da sua API (ou desabilite com
   `SALES_TOOL_ENABLED=false`).

Passo a passo detalhado no **[Guia Completo](docs/GUIA.md)**.

## Estrutura do projeto

```
.
├── docker-compose.yml       # api + worker + postgres + redis + qdrant + waha
├── Dockerfile
├── Makefile
├── requirements.txt
├── .env.example
├── data/knowledge/          # base de conhecimento Markdown (RAG) — EDITE AQUI
├── scripts/
│   ├── ingest_kb.py         # (re)indexa o Qdrant
│   └── migrate.py           # cria tabelas Postgres
├── src/chatbot/
│   ├── main.py              # FastAPI entry
│   ├── core/                # config, logging, observability, exceptions
│   ├── domain/              # stores, segments, dates, text (regras puras)
│   ├── agent/               # LLM + LangGraph (state, prompts, graph, runner)
│   ├── tools/               # @tool's expostas ao agente
│   ├── rag/                 # ingestion, retriever, embeddings, reranker
│   ├── memory/              # MemoryManager + extractor
│   ├── integrations/
│   │   ├── waha/            # cliente HTTP WAHA + modelos webhook
│   │   └── erp/             # cliente de exemplo de API externa
│   ├── infra/               # db (SQLAlchemy), redis, qdrant, queue
│   ├── workers/             # message_worker (consumidor)
│   └── api/                 # rotas FastAPI + middleware
├── docs/
│   ├── GUIA.md              # guia completo (o que faz + como adaptar)
│   └── ARCHITECTURE.md      # decisões técnicas
└── tests/
    ├── unit/                # domain (puros)
    └── integration/         # webhook smoke
```

## Tools disponíveis ao agente

| Tool | Quando usar |
|---|---|
| `resolver_codigo_da_filial(filial)` | Antes de qualquer consulta envolvendo UMA filial específica |
| `get_dates(intervalo)` | Para normalizar datas relativas (`hoje`, `ultima_terca`, `ultimos_15_dias`...) |
| `buscar_faturamento_itens(...)` | **Exemplo**: consulta a uma API REST externa com filtros dinâmicos |
| `retrieve_knowledge(query)` | Perguntas institucionais (história, missão, valores, lojas, etc.) |

### Adicionando uma nova tool

1. Crie `src/chatbot/tools/minha_tool.py` com `@tool`.
2. Importe em `src/chatbot/tools/__init__.py` e adicione a `ALL_TOOLS`.
3. Reinicie o worker.

## Observabilidade

Habilite `LANGFUSE_ENABLED=true` no `.env` e configure as chaves para ver cada
execução do grafo (steps, tokens, latência, custos). Logs locais: `make logs`.
Cada request tem `request_id` propagado via `structlog.contextvars`.

## Stack

| Componente | Papel |
|---|---|
| Python 3.11 | runtime |
| FastAPI / Uvicorn | webhook + admin |
| LangGraph | orquestração do agente |
| LangChain core | LLM + tools + messages |
| Gemini 2.5 Flash | LLM principal |
| Qdrant | vector store híbrida |
| BM25 (FastEmbed) | sparse vectors |
| Cohere Rerank | reranker (opcional) |
| Postgres + pgvector | sessão (checkpoint) + memória LP |
| Redis 7 | fila + dedup + debounce |
| WAHA | gateway WhatsApp |
| Langfuse | tracing (opcional) |
| structlog | logs estruturados |

## Testes

```bash
make test               # roda dentro do container
```

## Licença

MIT — veja [LICENSE](LICENSE). Use, adapte e distribua livremente.
