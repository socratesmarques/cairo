# API local V1

URL padrão: `http://127.0.0.1:8765`. O servidor só aceita loopback.
Todas as alterações usam JSON e o cabeçalho `X-Cairo-Client: web`.
Esse cabeçalho é uma proteção contra requisições de páginas externas, não autenticação.

| Método e rota | Resultado |
| --- | --- |
| `GET /api/health` | Estado do serviço e versão; não testa o modelo |
| `GET /api/config` | Provedor, modelo, workspace e permissão; nunca a chave |
| `GET /api/sessions` | Até 200 conversas, mais recentes primeiro |
| `POST /api/sessions` com `{}` | Nova conversa, resposta HTTP 201 |
| `GET /api/sessions/{id}` | Até 200 mensagens e 30 execuções recentes |
| `POST /api/runs` | Inicia execução, resposta HTTP 202 |
| `GET /api/runs/{id}` | Estado, resposta, erro e eventos em ordem |
| `POST /api/runs/{id}/cancel` com `{}` | Solicita cancelamento cooperativo |

Corpo de `POST /api/runs`:

```json
{"session_id":"id-da-conversa","message":"Analise os arquivos locais","mode":"swarm"}
```

`mode` aceita `normal` e `swarm`. Mensagens aceitam até 16000 caracteres.
Erros usam `{"error":"descrição"}`: 400 para entrada inválida, 403 para origem/host
ou cabeçalhos recusados, 404 para recurso ausente e 409 para limite de execução.
Não envie chaves nas mensagens.

Uma execução percorre `queued → running → completed | failed | cancelled`.
Há no máximo quatro execuções ativas e uma por conversa. A interface consulta
o estado periodicamente; a V1 não transmite tokens em streaming. Cancelamento
é checado entre operações. Uma chamada HTTP já iniciada termina ou alcança seu
timeout antes de liberar a execução; ações já concluídas não são desfeitas.

Os especialistas são executados por um pool de três threads. Cada etapa tem
limite de `CAIRO_MAX_STEPS` rodadas e cada retorno de modelo aceita no máximo
oito chamadas de ferramenta. O contexto inclui as últimas 12 mensagens, até
6000 caracteres por mensagem, e até 12000 caracteres de notas da sessão.
Dados antigos permanecem no SQLite; esses limites restringem o contexto enviado.

O arquivo `runtime.lock` impede dois serviços de coordenarem o mesmo banco.
No reinício, execuções interrompidas são marcadas como falha, sem repetição automática.


## Agenda 0.3

GET /api/reminders lista até 200 lembretes pendentes. POST /api/reminders recebe session_id, text (1..1000 caracteres) e due (ISO 8601 com fuso, futuro até 366 dias). POST /api/reminders/dismiss recebe id e session_id. As mutações exigem os mesmos cabeçalhos de proteção do chat. Datas persistem em UTC.
