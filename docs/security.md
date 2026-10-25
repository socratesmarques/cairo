# Segurança e fronteiras de confiança

Cairo V1 atende a uma pessoa em uma máquina local. Seu servidor HTTP é restrito ao loopback. Não o publique por proxy, túnel ou encaminhamento de porta: não há autenticação multiusuário ou política de acesso para um serviço público.

## Controles presentes

- Validação do host/origem e cabeçalho exigido nas operações de alteração reduzem chamadas indesejadas feitas por páginas externas.
- Caminhos de ferramentas passam por uma política central de workspace; entradas que escapam desse limite devem ser recusadas.
- Escrita de arquivos desabilitada por padrão e habilitada somente por `CAIRO_ALLOW_WRITE=true`.
- Ferramentas enumeradas e argumentos validados. Terminal opcional exige comando literal explícito do usuário; comandos executam com seus direitos Windows e não constituem sandbox de segurança.
- Timeout de provedor e limite de passos por agente reduzem esperas e ciclos sem fim.
- Eventos de execução e ferramentas ficam disponíveis para diagnóstico.

Esses controles são do aplicativo. Não isolam o processo Python de outros programas do mesmo usuário e não impedem que um processo local malicioso faça requisições ao servidor. A proteção de origem não substitui autenticação.

## Dados e segredos

Mantenha a chave do provedor em `.env` ou em uma variável de ambiente. O arquivo é ignorado pelo Git. Não envie a chave em mensagens nem a armazene como nota. Configure o workspace para uma pasta dedicada aos arquivos que Cairo pode acessar.

Sessões, mensagens, notas e traces ficam em SQLite na pasta `CAIRO_DATA_DIR`. Cairo não fornece criptografia em repouso; use as permissões e a proteção de disco do sistema operacional. Faça backup dessa pasta apenas com o aplicativo encerrado ou por um mecanismo consistente de backup do SQLite.

O conteúdo das conversas e das ferramentas pode ser enviado ao provedor escolhido. Ollama em loopback mantém essa comunicação na máquina; um endereço remoto transfere os dados para esse serviço. URLs de provedor são configuração de confiança do operador.

## Conteúdo não confiável

Arquivos, mensagens e respostas externas podem conter instruções que tentam modificar o comportamento dos agentes. Trate essas entradas como conteúdo não confiável. Permissões devem ser verificadas pelo aplicativo, independentemente do que o modelo afirmar. A revisão por outro agente não amplia permissões nem garante segurança.

Quando a escrita está habilitada, o modelo pode alterar arquivos permitidos durante a tarefa. Não há confirmação por arquivo. Use uma pasta de trabalho com arquivos recuperáveis e controle de versão quando apropriado.

## Antes de ampliar o escopo

Execução de código, navegador automatizado, mensagens externas e integrações com contas exigem controles próprios. Antes de adicioná-los, defina permissões por ação, tratamento de credenciais, isolamento adequado, limites de recursos e registro de resultados. Exposição em rede exige autenticação e autorização reais.

Relate falhas com passos mínimos de reprodução e dados sanitizados. Não inclua `.env`, bancos completos ou traces com informações pessoais em um relatório público.


## Aplicativos e voz (0.2)

`CAIRO_ALLOW_DESKTOP` controla a abertura e o gerenciamento de janelas de aplicativos cadastrados. O catálogo JSON é configuração de confiança do operador; não deve ser editável por entradas de chat ou documentos lidos pelos agentes. MasterAgent e SystemAgent têm acesso às ferramentas de desktop; os demais agentes não. Comandos completos reconhecidos no último texto do usuário passam pelo roteador local, antes do modelo. Conteúdo recuperado não passa por esse roteador.

O microfone inicia apenas por clique. A transcrição automática é opcional e usa o serviço do navegador, que pode transferir áudio para seu fornecedor. A transcrição torna-se mensagem somente após envio manual ou quando o usuário seleciona envio automático. Erros de reconhecimento impedem envio automático. A interface cancela o ditado ao trocar de conversa, esconder ou sair da página.

O controle básico de janelas é complementado pelo controle acessível opcional, que permite clicar, preencher campos, enviar atalhos e fechar janelas quando solicitado. O lançador usa listas de argumentos, sem shell. Abrir páginas usa o perfil normal do navegador e pode usar sua sessão já conectada.

## Terminal e controle interativo

Consulte [control-and-commands.md](control-and-commands.md). Comandos podem alterar qualquer recurso acessível à conta, independentemente das raízes de arquivos. UI Automation roda em processo separado para conter falhas de acessibilidade. O navegador automatizado usa contextos próprios por conversa; páginas e controles são evidência não confiável. Saídas e conteúdos lidos podem aparecer no histórico e ser enviados ao provedor do modelo.
