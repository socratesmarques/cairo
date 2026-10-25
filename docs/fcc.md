# Free Claude Code como gateway

Cairo continua responsável por agentes, contexto, memória, ferramentas, permissões e voz. FCC é um serviço separado: administra providers, credenciais upstream, roteamento, fallback e reasoning. Nenhum código ou pacote do FCC é incorporado ao Cairo.

## Arquitetura

`Orchestrator → AIService → Model.complete → FCCModel → HTTP local → FCC → provider`

O contrato existente `Model.complete(messages, tools) → Reply` permanece válido para demo, Ollama e OpenAI-compatible. `AIService` acrescenta uma entrada assíncrona com `asyncio.to_thread`, seleção por chamada e diagnóstico. O orquestrador usa a mesma camada nos modos normal e swarm. O adapter traduz mensagens e schemas para Messages, devolvendo chamadas de ferramentas ao Cairo. Blocos opacos de reasoning são conservados somente no histórico transitório da chamada, sem serem exibidos ou gravados como resposta.

## Configurar e iniciar

Na pasta do Cairo, configure `.env` (variáveis de ambiente têm precedência):

```dotenv
CAIRO_PROVIDER=fcc
FCC_BASE_URL=http://127.0.0.1:8082
FCC_AUTH_TOKEN=
FCC_MODEL=
CAIRO_TIMEOUT=90
CAIRO_MAX_OUTPUT_TOKENS=8192
```

Mantivemos `CAIRO_PROVIDER`, o nome já utilizado pelo Cairo; não é necessário `CAIRO_AI_PROVIDER`. Em modo FCC, `CAIRO_MODEL`, `CAIRO_BASE_URL` e `CAIRO_API_KEY` não são usados. `FCC_MODEL` vazio usa `default_model_id` do catálogo do FCC; se necessário, o adapter consulta `/` para obter o padrão. Um valor explícito deve constar no catálogo (ID ou provider_model_ref).

Instale o FCC separadamente seguindo o [README oficial](https://github.com/Alishahryar1/free-claude-code). Use o runtime exigido pela versão instalada do FCC; seu ambiente é independente do Python do Cairo. Inicie em um terminal:

```powershell
fcc-server
```

No Admin do FCC, configure provider e modelo e aplique a configuração. Se Proxy Authentication estiver ativada, copie o token do proxy para `FCC_AUTH_TOKEN` no ambiente local. Chaves dos providers permanecem no FCC. Em outro terminal, na pasta `C:\Users\Usuario\Documents\Cairo`:

```powershell
python -m cairo.desktop
```

O Cairo usa somente a API HTTP do servidor; nunca executa `fcc-claude`. Restrinja o servidor FCC ao loopback nas configurações dele se não precisar de acesso pela rede.

## Diagnóstico

- `GET http://127.0.0.1:8765/api/ai/health`: online/offline, URL, autenticação, quantidade e lista de modelos, modelo selecionado e `ready`.
- `GET http://127.0.0.1:8765/api/ai/models`: catálogo e modelo padrão; erros retornam HTTP 502 com código e mensagem segura.
- `/api/health` continua verificando apenas o processo Cairo.

`ready=true` confirma catálogo acessível e modelo selecionável, não a disponibilidade upstream para inferência. `request_accepted` indica que uma requisição com token foi aceita, não prova que a autenticação está habilitada. `not_required` indica sucesso sem token. Timeout/conexão interrompida produzem estado `unreachable`, sem afirmar que o processo está desligado.

Erros de provider usam `ModelError` com códigos `offline`, `timeout`, `authentication`, `model_unavailable`, `http_error`, `invalid_http`, `unexpected_response`, `network`, `output_limit` ou `invalid_request`. Corpos de erro upstream e tokens não são incluídos nas mensagens ao usuário. Respostas truncadas por limite de saída não executam ferramentas parciais. Não há fallback silencioso para demo.

## Exemplo

```python
import asyncio
from cairo.config import Settings
from cairo.models.service import AIService

async def main():
    ai = AIService(Settings.from_env())
    response = await ai.chat(messages=[{"role": "user", "content": "Olá"}])
    print(response.content)

asyncio.run(main())
```

Para selecionar por chamada, acrescente `model="ID retornado pelo catálogo"`. Isso não altera a configuração global. `ai.list_models()` e `ai.health()` são operações síncronas; em um servidor assíncrono, use `asyncio.to_thread`.

## Testar

```powershell
python -m unittest discover -s tests -v
python -m compileall -q cairo tests
node --test tests/test_voice.cjs
```

Teste real opcional, com FCC configurado e executando:

```powershell
$env:CAIRO_PROVIDER='fcc'
$env:CAIRO_TEST_FCC='1'
python -m unittest discover -s tests -p test_fcc_live.py -v
```

O teste real usa o padrão atual do FCC, independentemente de `FCC_MODEL`, envia `Responda somente: CAIRO OK` e exige resposta exata. É ignorado quando desativado ou quando FCC está offline; autenticação inválida e falhas de inferência fazem o teste falhar. Pode consumir a cota do provider configurado.

## Contrato e limites

Verificado no código público do FCC em 24/10/2026: [rotas](https://github.com/Alishahryar1/free-claude-code/blob/main/src/free_claude_code/api/routes.py), [autenticação](https://github.com/Alishahryar1/free-claude-code/blob/main/src/free_claude_code/api/dependencies.py) e [catálogo](https://github.com/Alishahryar1/free-claude-code/blob/main/src/free_claude_code/api/model_catalog.py). Existem `/v1/models`, `/v1/messages` e `/v1/responses`. Este adapter usa apenas o catálogo `?view=messages` e Messages não streaming, com Bearer quando configurado.

Somente texto e ferramentas locais; sem imagens, streaming ou ferramentas executadas pelo servidor FCC. URLs são origens HTTP(S) locais sem credenciais, query ou prefixo `/v1`. Redirecionamentos e proxies do sistema são desativados. Respostas limitadas a 2 MB. O catálogo é consultado a cada chamada para acompanhar alterações no FCC; catálogos paginados são rejeitados explicitamente. Timeout é aplicado por requisição HTTP, não ao turno completo. Cancelar a coroutine não interrompe imediatamente a requisição na thread. Fallback e reasoning continuam sob controle do FCC.

Próximas extensões possíveis, fora desta entrega: streaming e cache curto do catálogo, se a latência justificar. Não foram adicionados memória, voz, subagentes ou ferramentas novos.
