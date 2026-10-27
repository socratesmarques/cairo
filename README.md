# Cairo
# prox atualz. 0.9
## Novidades — versão 0.8

A **Central do dia** reúne tarefas com prioridade e prazo, notas editáveis, agenda com adiamento, temporizador de foco persistente, calculadora, conversão de unidades e ferramentas de texto. Abra pela barra lateral; **Explorar comandos** mostra exemplos pesquisáveis. As funções locais funcionam sem IA e os dados ficam separados por conversa.

Exemplos: Adicione tarefa: Revisar orçamento, Meu dia, Salve nota Ideias: Preparar uma apresentação, Inicie foco de 25 minutos, Calcule (150 + 35) * 2, Converta 2,5 km para m. Veja [o guia da versão 0.8](docs/daily-0.8.md) para limites, exportação e alertas.


**Atualização 0.7:** posicionamento geral de aplicativos instalados, incluindo
apps da Store, nos quatro lados, cantos, centro, monitores e coordenadas.
Veja [os comandos de janelas](docs/windows-0.7.md).

**Correção 0.6.1:** comandos de música no aplicativo desktop, abrir e posicionar
janelas à direita/esquerda e continuidade da escuta após erros de execução.
Veja [os exemplos e limites](docs/desktop-0.6.1.md).

**Atualização 0.6:** carregamento do histórico antigo na conversa, importação de
JSON, restauração verificável de backups e correções de rascunhos e estado entre
abas. Consulte [as novidades e instruções](docs/daily-0.6.md).

**Atualização 0.5:** temas claro/escuro, histórico pesquisável pelo conteúdo,
conversas fixadas e arquivadas, rascunhos por conversa, respostas formatadas,
exportação completa e cópia verificável do histórico. Consulte
[o guia de uso diário](docs/daily-0.5.md).

**Atualização 0.4:** diagnóstico local, aviso de reinicialização pendente, atalhos
pessoais, copiar/reutilizar pedidos e health checks de modelos. Consulte
[a revisão completa e os limites](docs/review-0.4.md).

Uma plataforma pessoal de agentes de IA, com identidade própria, núcleo Python e interface web local. Esta V1 foi implementada de forma independente, a partir de conceitos gerais de sistemas de agentes. Não contém código ou branding do OpenJarvis.

## Começar

Requisitos: **Python 3.11 ou superior** e um navegador moderno. O núcleo usa a biblioteca padrão do Python; não exige instalar pacotes para executar.

No PowerShell, a partir desta pasta:

```powershell
Copy-Item .env.example .env
python -m cairo
```

No Linux ou macOS:

```sh
cp .env.example .env
python3 -m cairo
```

Abra <http://127.0.0.1:8765>. Também há lançadores em `scripts/run.ps1` e `scripts/run.sh` (execute este último com `sh scripts/run.sh`). Para abrir o navegador junto com o servidor, use `python -m cairo.desktop`. Para escolher outra porta:

```sh
python -m cairo --host 127.0.0.1 --port 8766
```

O modo inicial é **demo** para conversas livres; comandos locais de aplicativos funcionam sem IA. O demo é determinístico: permite verificar chat, ferramentas, persistência e execução dos agentes sem baixar um modelo ou configurar uma chave. As respostas do demo não substituem as respostas de um modelo. Para conversar com uma IA, configure um dos provedores abaixo e reinicie Cairo.

## Conectar um modelo

Edite `.env`. Variáveis já definidas no ambiente têm precedência sobre o arquivo.

### Ollama local

Com Ollama instalado, em execução e com um modelo já disponível:

```dotenv
CAIRO_PROVIDER=ollama
CAIRO_MODEL=qwen2.5:7b
CAIRO_BASE_URL=http://127.0.0.1:11434
CAIRO_API_KEY=
```

O nome acima é um exemplo: use o nome exato de um modelo instalado no seu Ollama. Cairo não baixa modelos automaticamente.

### API compatível com OpenAI

```dotenv
CAIRO_PROVIDER=openai-compatible
CAIRO_MODEL=nome-do-modelo-do-seu-provedor
CAIRO_BASE_URL=https://api.openai.com/v1
CAIRO_API_KEY=sua-chave-local
```

Use a URL base e o modelo disponibilizados pelo seu provedor. A integração utiliza Chat Completions. O tráfego dos prompts e dos resultados de ferramentas passa pelo provedor escolhido; um endpoint remoto recebe esses dados. Não coloque chaves no chat, no controle de versão ou em capturas de tela.

## O que funciona nesta V1

- Chat web local com histórico persistente, seleção de modo e acompanhamento da execução dos agentes.
- **Normal:** Master Agent chama ferramentas conforme necessário e responde.
- **Swarm:** Master planeja, DeveloperAgent, ResearchAgent e SystemAgent trabalham em paralelo, Reviewer revisa os resultados e Master produz a resposta final.
- Adaptadores para demo, Ollama e APIs OpenAI-compatible.
- Registro de ferramentas e skills, leituras e listagens de arquivos, escrita opcional, informações do sistema e notas persistentes.
- SQLite para sessões, mensagens, notas, execuções e traces.
- Limites de iteração, validação de argumentos, operações de arquivos restritas ao workspace e escrita desabilitada por padrão.
- Componentes extensíveis para agendamento em processo, integrações e abertura da interface pelo navegador.

O ResearchAgent lê arquivos, páginas públicas e resultados Google quando habilitados. O DeveloperAgent analisa e altera arquivos permitidos. O SystemAgent abre aplicativos e controla janelas e controles acessíveis. CMD e PowerShell aceitam comandos explícitos do usuário. Veja [controle de aplicativos, terminal e navegador JavaScript](docs/control-and-commands.md).

O modo swarm usa mais chamadas e contexto do modelo que o modo normal. Em um modelo local, três chamadas simultâneas podem competir por memória e capacidade de processamento. Escolha o modo normal para pedidos simples.

## Arquivos, memória e permissões

`CAIRO_WORKSPACE` define a pasta acessível pelas ferramentas de arquivos. `CAIRO_DATA_DIR` define a pasta de dados persistentes. Os padrões, relativos à pasta de execução, são `workspace/` e `storage/`. Os lançadores entram na raiz do projeto antes de executar Cairo.

Para permitir criação ou alteração de arquivos **dentro do workspace**, configure:

```dotenv
CAIRO_ALLOW_WRITE=true
```

Essa configuração é uma permissão global para as ferramentas de escrita; não há aprovação individual por arquivo. Mantenha cópias dos arquivos importantes. Os demais dados persistentes, como histórico e notas, são gravados normalmente mesmo com escrita de workspace desabilitada.

Histórico, notas e traces ficam no computador em SQLite, sem criptografia própria do aplicativo. Traces registram etapas e operações; mensagens e notas contêm o conteúdo das conversas. Logs rotativos em traces.jsonl registram metadados, sem chaves nem argumentos de ferramentas. Não use arquivos sensíveis em testes sem considerar o provedor configurado. Consulte [a política de segurança](docs/security.md).

## Estrutura

```text
Cairo/
├── cairo/
│   ├── core/           # Ciclo de execução e logs estruturados
│   ├── agents/         # Master, especialistas e Reviewer
│   ├── orchestrator/   # Roteamento e execução normal/swarm
│   ├── models/         # Contrato de modelos e adaptadores
│   ├── memory/         # Persistência SQLite
│   ├── tools/          # Registro e ferramentas
│   ├── skills/         # Instruções reutilizáveis dos agentes
│   ├── scheduler/      # Agendamento em processo
│   ├── sandbox/        # Permissões e limites de arquivos
│   ├── integrations/   # Contratos para integrações futuras
│   ├── api/            # Servidor HTTP local
│   ├── web/            # Interface de chat
│   ├── desktop/        # Abertura pelo navegador
│   ├── config/         # Configuração validada
│   └── storage/        # Backup consistente do SQLite
├── storage/
├── tests/
├── docs/
├── scripts/
├── .env.example
├── AGENTS.md
└── pyproject.toml
```

Consulte [a arquitetura](docs/architecture.md) para o plano de evolução e [a API local](docs/api.md) para contratos, limites e cancelamento.

## Verificar

Na raiz do projeto:

```sh
python -m unittest discover -s tests -v
python -m compileall -q cairo tests
```

Os testes básicos devem funcionar sem internet, credenciais ou Ollama. A integração real depende da disponibilidade e do comportamento do endpoint configurado. Erros de conexão, autenticação, formato ou timeout são reportados; não há fallback silencioso para respostas demo.

## Limites da V1

É uma base funcional para uso local individual, preparada para evolução. Não é um serviço pronto para exposição pública: não possui autenticação multiusuário, isolamento de processos, fila durável de trabalho, retomada de tarefas após reinício ou distribuição entre máquinas. Lembretes persistentes podem ser gerenciados no chat e no painel; exigem a interface aberta para avisar. O módulo desktop abre o navegador; não é um aplicativo nativo empacotado.

Primeiros passos recomendados: testar em demo, conectar seu modelo, experimentar o modo normal em uma pasta de trabalho pequena e depois comparar uma tarefa equivalente em swarm.

## Instalar como pacote

Opcionalmente, execute `python -m pip install .` para instalar os comandos `cairo` e `cairo-desktop`. O build usa setuptools; não há dependências de execução. Execute os comandos numa pasta dedicada para manter `.env`, workspace e storage juntos. O pacote wheel pode ser instalado diretamente com pip.


## Aplicativos e microfone — versão 0.2

A instalação em Documentos\Cairo já foi habilitada para controle de aplicativos. Em uma instalação nova, copie `.env.example` para `.env`. `CAIRO_ALLOW_DESKTOP=true` habilita o recurso; `false` o desativa.

Abra com `Abrir Cairo.cmd` ou `python -m cairo.desktop`. O lançador prefere Chrome quando instalado, para compatibilidade de voz.

Digite ou dite:

- “Abra o Google Chrome.”
- “Abra o YouTube Music.”
- “Abra o Google Chrome e abra o YouTube Music.”
- “Pesquise João Gilberto no YouTube Music.”
- “Abra o YouTube Music no Edge.”
- “Abra a calculadora.” / “Abra o bloco de notas.”
- “Minimize o Chrome.” / “Maximize o Chrome.” / “Restaure o Chrome.” / “Foque o Chrome.”
- “Quais aplicativos você controla?”

Essas formas de comando são executadas diretamente, mesmo no modo demo. O roteador aceita apenas comandos completos reconhecidos e executa cada ação uma vez, inclusive quando o modo multiagente está selecionado. Pedidos mais livres dependem do modelo configurado. Aplicativos também podem ser descobertos pelo menu Iniciar. O terminal usa uma ferramenta separada com comando literal do usuário; veja o guia atualizado.

Clique em **Microfone**, permita o acesso no navegador e fale em português. O texto aparece no campo de mensagem. Clique em **Enviar**, ou marque **Enviar ao terminar de falar** antes de ditar para executar automaticamente. O botão **Terminar ditado** encerra a captura; trocar de conversa ou ocultar a página a cancela. Cada captura dura até 30 segundos. No ditado avulso, Cairo não fica ouvindo em segundo plano. A escuta contínua opcional é descrita abaixo. Cairo não grava áudio em arquivos.

O reconhecimento usa o serviço disponível no navegador, pode enviar áudio ao serviço do fornecedor e pode exigir internet. A qualidade depende do microfone, navegador e idioma. No navegador integrado, se o serviço não estiver disponível, abra a mesma página no Chrome. Não há palavra de ativação nem reconhecimento de voz offline nesta versão.

O controle de janelas funciona para janelas clássicas do Windows que pertencem ao executável cadastrado. Se houver várias, a primeira na ordem de janelas é usada. Aplicativos da Microsoft Store podem usar outro processo; nesses casos Cairo informa que não encontrou uma janela compatível. O Windows pode recusar a mudança de foco. Abrir YouTube Music ou pesquisar não inicia uma música automaticamente; escolha a faixa na página.

A abertura confirma o envio da solicitação. Com CAIRO_ALLOW_APP_CONTROL habilitado, o Cairo também inspeciona controles acessíveis, preenche campos e aciona botões; confira o resultado por nova inspeção.

Teste da camada de voz (Node.js opcional, somente para desenvolvimento):

```sh
node tests/test_voice.cjs
```

Referência do reconhecimento de fala: [SpeechRecognition — MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).


## Dia a dia — versão 0.3

- **Lembretes persistentes:** “Me lembre em 10 minutos de beber água”, “Liste meus lembretes”, ou formulário em **Ferramentas do dia a dia**. A data do formulário usa o fuso do navegador. Lembretes atrasados aparecem ao reabrir Cairo. Conclua/cancele no painel. Não executam ações agendadas, não despertam o computador e não avisam com a interface fechada. A agenda do painel reúne as conversas deste usuário local; ferramentas dos agentes acessam apenas a conversa atual.
- **Voz de saída:** botão Ouvir em cada resposta, opção de ler novas respostas automaticamente e botão Parar voz. Usa vozes disponíveis no navegador/sistema, com limite de 12 mil caracteres por leitura; não garante voz offline. O ditado é interrompido antes da leitura e a leitura para antes de ditar.
- **Pesquisa local:** `search_files` encontra nomes ou conteúdo UTF-8 dentro do workspace. Limites: 2.000 entradas, 100 resultados, 64 KiB por arquivo, uma ocorrência por arquivo. Retorna quantidade ignorada e indicação de limite atingido. Não segue links/junctions.
- **Pastas e arquivos:** `create_directory` e `write_file`, com `CAIRO_ALLOW_WRITE=true`. Habilitado na instalação atual a pedido do usuário, somente no workspace configurado. Não concede acesso de escrita ao Windows inteiro.
- **Google:** “Pesquise receitas de pão no Google” abre a pesquisa no Chrome. O agente não lê nem resume esses resultados automaticamente.
- **Exportação:** botão Exportar conversa baixa JSON da janela de histórico atual (até 200 mensagens e 30 execuções); não é um backup integral do banco.

Pesquisa local e criação de arquivos via pedidos livres requerem modelo real com suporte a ferramentas. Lembretes nas formas documentadas e comandos de navegador funcionam sem modelo. Configuração do provedor foi preservada: esta atualização não baixa modelos nem muda silenciosamente para Ollama.

Limites atuais: não há controle visual universal, desvio de UAC/CAPTCHA, reconhecimento de voz offline, palavra de ativação, notificações com Cairo fechado ou pacote desktop nativo. Controle acessível de aplicativos, navegador JavaScript e terminal são opcionais: [guia atualizado](docs/control-and-commands.md).


## Escuta contínua

Abra Cairo no Chrome, deixe o campo de mensagem vazio e clique em **Escuta contínua**. Permita o microfone quando o navegador solicitar. Cada frase finalizada por uma pausa é enviada automaticamente, sem precisar clicar em Enviar. Exemplo: “Abra Google”, aguarde **Ouvindo próximo comando**, depois “Abra YouTube Music”.

O modo usa ciclos de reconhecimento em português. Após cada comando, aguarda a execução e eventual leitura da resposta, depois reabre o microfone. Durante a execução e a voz de saída não captura novas instruções; não existe fila de fala. Períodos sem fala rearmam o reconhecimento. Não há palavra de ativação: conversas próximas podem ser interpretadas como pedidos enquanto estiver ouvindo.

Clique **Parar escuta** ou diga **“parar escuta”** / **“pare de ouvir”** enquanto estiver ouvindo. O comando de parada é tratado localmente, sem chamar o agente. Trocar de conversa, abrir nova conversa, sair da página ou encontrar erro de microfone/execução também desliga o modo. Uma recarga nunca o ativa sozinha. Texto já digitado precisa ser enviado ou limpo antes da ativação.

Ao mudar para um aplicativo aberto por Cairo, o modo continua habilitado enquanto a página permanecer aberta. Navegadores podem suspender abas em segundo plano; isso não é um serviço de escuta do Windows. Se a aba for suspensa, volte ao Cairo. Reconhecimento depende do navegador e pode enviar áudio ao serviço do fornecedor; não é offline. Use o indicador de escuta como referência. O ditado avulso mantém seu comportamento anterior.

Validação: 49 testes Python e 10 testes JavaScript, incluindo comandos sequenciais, espera durante execução/voz, silêncio, parada falada, bloqueio de permissão e rejeição de eventos atrasados. Captura acústica real e continuidade com navegador em segundo plano precisam de teste com o microfone do usuário; testes automatizados usam reconhecimento simulado.
# Gateway de modelos Free Claude Code

Novas opções: acesso por caminho absoluto fora do workspace, descoberta de aplicativos instalados e leitura dos resultados do Google. Configuração, exemplos e condição de verificação humana do Google em [docs/expanded-access.md](docs/expanded-access.md).

JavaScript e operações de arquivos agora estão disponíveis como recursos configuráveis: [guia de navegador e arquivos](docs/browser-and-files.md). Inclui cópia, movimentação, renomeação, edição com backup, busca e lixeira recuperável nas pastas cadastradas.

As novas ações do dia a dia incluem abrir Downloads e outras pastas pessoais, consultar clima e previsão, ler páginas públicas e controlar mídia/volume. Exemplos e permissões: [docs/daily-actions.md](docs/daily-actions.md).

A integração opcional com FCC usa HTTP local, preservando os agentes e ferramentas do Cairo. Configure `CAIRO_PROVIDER=fcc` e `FCC_BASE_URL=http://127.0.0.1:8082`; deixe `FCC_MODEL` vazio para acompanhar o padrão do FCC. Instruções completas, autenticação, diagnóstico, testes e exemplo assíncrono: [docs/fcc.md](docs/fcc.md).


## Controle de aplicativos e terminal

[Guia de configuração, exemplos e limites](docs/control-and-commands.md): UI Automation isolada, CMD/PowerShell com saída e cancelamento, e navegador JavaScript persistente por conversa.
