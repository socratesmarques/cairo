# Arquitetura do Cairo

## Objetivo e escopo

Cairo deve evoluir para um assistente pessoal usado diariamente. A V1 entrega um fluxo completo de interface, coordenação, modelos, ferramentas e persistência. Seus componentes têm fronteiras explícitas para permitir trocar provedores e ampliar capacidades sem reescrever a interface.

O projeto foi implementado de forma independente. A inspiração é conceitual: agente principal, especialistas, ferramentas, memória e interface. Não há dependência de código do OpenJarvis.

## Fluxo de uma tarefa

```text
Navegador local
    │ requisição HTTP
    ▼
API → configuração / memória / traces
    │
    ▼
Orquestrador
    ├─ normal: Master → ferramentas → Master → resposta
    │
    └─ swarm: Master (plano)
                    │
           ┌────────┼─────────┐
           ▼        ▼         ▼
       Developer Research   System
           └────────┼─────────┘
                    ▼
                 Reviewer
                    ▼
             Master (síntese)
                    │
                    ▼
            memória + interface
```

Os especialistas trabalham em paralelo dentro de uma execução swarm. A revisão ocorre depois dos resultados dos especialistas. Reviewer avalia evidências e limitações; a síntese final cabe ao Master. A revisão é uma avaliação do modelo, não uma prova de correção ou uma fronteira de segurança.

## Módulos

| Módulo | Responsabilidade |
| --- | --- |
| `core/` | Ciclo de execução e logs estruturados |
| `agents/` | Identidades e instruções dos agentes |
| `orchestrator/` | Roteamento normal/swarm e coordenação do ciclo de execução |
| `models/` | Interface comum e adaptadores demo, Ollama e OpenAI-compatible |
| `memory/` | Operações SQLite para sessões, mensagens, notas, execuções e traces |
| `tools/` | Catálogo, validação e execução das capacidades disponíveis |
| `skills/` | Instruções reutilizáveis associadas às capacidades dos agentes |
| `scheduler/` | Callbacks recorrentes enquanto o processo está ativo |
| `sandbox/` | Permissões de ferramentas e confinamento de caminhos |
| `integrations/` | Contrato para adaptadores de serviços externos |
| `api/` | Protocolo HTTP local e validação das requisições |
| `web/` | Chat, sessões e apresentação do andamento dos agentes |
| `desktop/` | Inicialização da experiência pelo navegador |
| `config/` | Carregamento e validação de configuração |
| `storage/` | Backup consistente; storage/ na raiz guarda dados gerados |
| `tests/` | Verificações determinísticas dos fluxos e fronteiras |

## Modelos e ferramentas

O agente usa uma abstração de provedor; o coordenador não precisa conhecer detalhes HTTP de cada backend. O demo produz respostas determinísticas para exercícios e testes. Ollama e OpenAI-compatible fazem chamadas aos endpoints configurados. Uma falha de backend deve ser visível, sem troca automática por demo.

Chamadas de ferramenta passam pelo registro e pelas permissões. O modelo solicita uma operação; o aplicativo decide se ela pode executar. A configuração limita o número de passos por agente e o tempo de chamada ao provedor. Não há execução de shell arbitrário.

Ferramentas de arquivos operam em um workspace delimitado. Leitura/listagem, informações do sistema e notas atendem aos primeiros fluxos. A escrita de arquivos exige configuração explícita. Skills complementam as instruções dos agentes e não podem ampliar as permissões do aplicativo.

O ResearchAgent trabalha com evidência local. Para pesquisa externa futura, uma integração deverá expor busca/leitura como ferramentas, conservar atribuição de fontes e aplicar seus próprios controles de saída de dados.

## Persistência e observabilidade

SQLite fornece armazenamento local simples para sessões, mensagens, notas, execuções e traces. Cada execução pode ser acompanhada pela interface; eventos de agentes e ferramentas permitem compreender o progresso e diagnosticar falhas.

Histórico de conversa e notas são recursos distintos. O histórico permite continuar uma sessão; notas guardam informações explícitas reutilizáveis. Não há memória vetorial, indexação semântica ou aprendizado automático dos hábitos do usuário nesta versão.

Os dados ficam sem criptografia própria do Cairo. O usuário controla a pasta de armazenamento e seus backups. Chamadas a provedores remotos transferem o contexto necessário ao endpoint escolhido.

## Extensões implementadas como componentes

- O scheduler executa callbacks recorrentes no processo ativo. Não persiste a agenda nem recupera execuções perdidas após reinício.
- O contrato de integração define a fronteira para adaptadores futuros. Não implica conectores de email, calendário ou nuvem já disponíveis.
- O módulo desktop abre a interface no navegador. Empacotamento nativo e atualização automática estão fora da V1.
- O sandbox é uma política de acesso no aplicativo; não é um ambiente isolado pelo sistema operacional.

## Evolução planejada

1. **Uso diário local:** retenção e exportação de histórico, cancelamento interruptível de chamadas HTTP, testes de compatibilidade com diferentes modelos e melhor recuperação de falhas.
2. **Conhecimento e integrações:** indexação local, pesquisa com fontes, conectores opt-in e permissões por ferramenta/operação.
3. **Automação confiável:** agenda persistente, fila durável, tarefas idempotentes, retomada e políticas de aprovação para ações externas.
4. **Isolamento e distribuição:** processos separados para ferramentas, autenticação, autorização por usuário, cofre de segredos e workers remotos.
5. **Experiência desktop:** pacote instalável, notificações, atualizações verificadas e recursos de acessibilidade.

Cada fase deve preservar compatibilidade dos dados ou incluir migração explícita. A V1 não antecipa serviços distribuídos ou dependências pesadas antes de haver uma necessidade concreta.

## Referências de protocolo

Adaptadores implementados a partir dos contratos públicos: [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) e [Ollama Chat](https://docs.ollama.com/api/chat). Nenhum código do OpenJarvis foi usado.


## Extensão 0.2: desktop e ditado

`orchestrator/desktop_commands.py` reconhece comandos completos locais antes do fluxo de modelos. `integrations/desktop_control.py` descobre executáveis em caminhos cadastrados, abre aplicativos com argumentos estruturados e usa APIs Win32 para ações de janela. `config/desktop.json` centraliza aplicativos, aliases e sites. Todas as ações também passam pelo registro de ferramentas e por CAIRO_ALLOW_DESKTOP.

`web/voice.js` isola o ciclo de SpeechRecognition da interface: início por clique, parciais, resultados finais, cancelamento e falhas. `web/app.js` integra a transcrição ao editor e ao envio opcional. Nenhuma rota HTTP recebe áudio; a escolha do serviço de reconhecimento pertence ao navegador.

Referências: [ShowWindowAsync](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindowasync), [SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow), [SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).


## Extensões 0.3

Reminders é um repositório SQLite separado em scheduler/reminders.py, com migração aditiva. Criação valida sessão, fuso, data futura, tamanho e quota. Consultas dos agentes são isoladas por sessão. O painel local lista até 200 lembretes pendentes de todas as sessões e calcula vencimento a cada cinco segundos. Não há execução de ações em background. O estado dismissed é preservado.

A pesquisa de arquivos usa WorkspacePolicy para cada candidato e percorre no máximo 2.000 entradas sem seguir links. A interface usa speechSynthesis para saída e SpeechRecognition para entrada, nunca simultaneamente.
# Integração FCC

A camada de modelos agora expõe `AIService`: o orquestrador depende deste serviço, que utiliza o contrato existente `Model.complete`. `FCCModel` é o único ponto que conhece a API HTTP do Free Claude Code. A tradução de mensagens e ferramentas fica em `models/fcc_protocol.py`; os erros seguros em `models/errors.py`. Providers anteriores mantêm seus contratos. Consulte [fcc.md](fcc.md) para configuração e limites.

