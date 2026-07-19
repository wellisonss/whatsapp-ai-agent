# Arquitetura

## Princípios

1. **Camadas explícitas (Clean / Hexagonal)** — domínio, agente, integrações e infra são separados; tools e prompts ficam isolados; tudo testável sem rede.
2. **Estado por sessão** — nenhum mutação global. Conversa por `chat_id` é mantida no `thread_id` do checkpointer LangGraph.
3. **Webhook nunca processa** — apenas enfileira. Toda lógica acontece no worker (resiliente a picos, retries, redeploys).
4. **Tudo via `pydantic-settings`** — uma única classe `Settings` carregada do `.env` é a fonte da verdade.

## Fluxo de uma mensagem

```
WhatsApp ─► WAHA ─► POST /webhook/waha
                         │
                         ├── valida payload (pydantic)
                         ├── ignora fromMe / vazio
                         ├── enqueue() em Redis Streams
                         │      ├── SET NX dedup_key (1h TTL)
                         │      └── buffer textual + debounce key
                         └── responde 200 (≤ 50ms)

(loop)
Worker  ─► xreadgroup
          ├── espera debounce (2s sem novas msgs do mesmo chat)
          ├── drena buffer (concatena mensagens em sequência)
          ├── start_typing(WAHA)
          ├── run_agent(chat_id, text)
          │     ├── load_memory: busca user_facts no Postgres
          │     ├── agent: LLM (com tools bound) chama ou responde
          │     ├── tools: ToolNode executa tool calls
          │     │     ├── resolver_codigo_da_filial (puro)
          │     │     ├── get_dates (puro)
          │     │     ├── buscar_faturamento_itens (HTTP ERP)
          │     │     └── retrieve_knowledge (Qdrant hybrid + rerank)
          │     └── format: limpa glyphs unsafe pro WhatsApp
          ├── extract_facts → MemoryManager.add (best-effort)
          ├── send_chunked(WAHA) (1600 chars/parte)
          └── stop_typing(WAHA)
```

## Decisões técnicas

### Por que LangGraph?

- **Persistência nativa de estado** via checkpointer (Postgres) → conversa segura entre redeploys, sem hack manual de SQLite.
- **Modelo de grafo** explicita o fluxo `agent ⇄ tools` e permite adicionar nodes (router, validators, human-in-the-loop) sem reescrever.
- **Streaming token-a-token** se quisermos responder progressivamente no futuro.
- **Padrão de mercado** em 2026 — ecosistema (LangSmith, Langfuse, OpenTelemetry) é first-class.

### Por que Redis Streams (e não Celery)?

- Dedup nativo via `SET NX` + dedup_key, mais barato e mais previsível que beat-loop do Celery.
- Streams têm consumer groups com ack/replay — semântica adequada para webhooks.
- Footprint menor (1 container Redis vs. broker + worker + flower).

### Por que Qdrant em vez de pgvector ou Chroma?

- **Hybrid search nativo** (sparse + dense em uma query) sem hacks.
- **Performance e quotas** muito superiores a pgvector para 100k+ chunks.
- **API HTTP** + persistência em volume — operacional simples no compose.
- ChromaDB em produção tem histórico de instabilidades em concorrência.

### Por que duas camadas de memória?

- *Session memory* (LangGraph checkpointer): histórico vivo da conversa, mensagens cruas. Reset por `thread_id` se quisermos limpar.
- *Long-term memory* (`user_facts` em Postgres): fatos extraídos por LLM (preferências, papel, lojas favoritas). Sobrevive a "esquecer a sessão".
- Separar evita o classic anti-pattern de injetar histórico cru em todo prompt (cara, ruidoso e vaza dados antigos).

### Por que extrator de fatos com JSON estrito?

- LLMs são ótimos para sumarização/extração mas péssimos para "lembrar tudo".
- Pedimos só **fatos estáveis** (preferências, papel, métricas favoritas) e até 5 por turno.
- Saída em JSON parseado com fallback silencioso garante que nunca quebre o fluxo.

### Por que worker separado da API?

- Resposta ao WAHA precisa ser instantânea (senão WAHA reenvia → loop).
- Reagente do agente pode levar 5-30s; isolar protege a API de timeouts.
- Permite escalar API e worker independentemente (mais workers em horários de pico).

## Pontos de extensão

| Quero... | Onde mexer |
|---|---|
| Adicionar tool | `src/chatbot/tools/*.py` + registrar em `tools/__init__.py` |
| Mudar prompt | `src/chatbot/agent/prompts.py` |
| Adicionar node ao grafo | `src/chatbot/agent/graph.py` (`add_node` + edges) |
| Trocar LLM | `src/chatbot/agent/llm.py` |
| Trocar reranker | `src/chatbot/rag/reranker.py` |
| Novo tipo de extração de memória | `src/chatbot/memory/extractor.py` |
| Novo cliente externo | `src/chatbot/integrations/<svc>/client.py` |

## Armadilhas comuns que este projeto já evita

| Armadilha | Como é tratado aqui |
|---|---|
| Estado global de usuário → race entre webhooks concorrentes | `thread_id=chat_id` no LangGraph; estado por checkpointer; sem singleton mutável |
| Webhook reenviado pelo WAHA processa duas vezes | `SET NX dedup:<message_id>` com TTL de 1h |
| Mensagens em sequência viram N respostas | Buffer + debounce: 2s sem novas msgs → concatena e responde uma vez |
| `print()` espalhado, sem correlação | `structlog` JSON com `request_id`/`chat_id` em context vars |
| `os.getenv` em qualquer arquivo | `Settings` única com `lru_cache` |
| Base vetorial sem chunking estruturado | Markdown header splitter + recursive char + hybrid search + rerank |
| Sem observabilidade | Langfuse callback opcional |

## Caminhos futuros (não implementados, mas previstos)

- **Streaming SSE** da resposta para o frontend de admin (LangGraph já suporta `astream_events`).
- **Avaliação automática** com `langsmith` ou `ragas` (testes de regressão de RAG/agente).
- **Cache de tools** (HTTP cache em Redis para `get_sales_report` com mesmas params em 60s).
- **Multi-modal** (imagens/áudio do WhatsApp via Gemini 2.5).
- **Guardrails** de saída (Pydantic structured output em respostas críticas).
- **Migrações Alembic** quando o schema crescer (`user_facts` é simples hoje).
