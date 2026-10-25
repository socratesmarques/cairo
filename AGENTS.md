# Instruções de desenvolvimento do Cairo

Cairo é uma plataforma pessoal de agentes, implementada de forma independente. Preserve seu nome e identidade. Não copie código proprietário, chaves, prompts privados ou branding de outros projetos.

## Convenções

- Python 3.11+, biblioteca padrão como base. Justifique novas dependências pelo benefício concreto.
- Mantenha contratos de modelos em `cairo/models`, coordenação em `cairo/orchestrator`, agentes em `cairo/agents`, persistência em `cairo/memory` e regras de acesso em `cairo/sandbox`.
- Interface e rotas HTTP não devem conter lógica de seleção de agentes, autorização de ferramentas ou SQL.
- Ferramentas têm nomes estáveis, argumentos validados e resultados estruturados. Registre novas ferramentas no mesmo catálogo usado pelo agente.
- Parâmetros variáveis pertencem à configuração; não espalhe URLs, limites ou modelos pelo código.
- Erros devem identificar a operação que falhou sem expor segredos. Não transforme falhas em resultados vazios aparentemente válidos.
- Preserve isolamento entre sessões e correlação entre execução, agente e eventos.
- Atualize a documentação quando um comportamento público ou uma variável de configuração mudar.

## Segurança

- Servidor restrito ao loopback. Não habilite exposição na rede sem implementar autenticação, autorização e revisar as fronteiras de confiança.
- Valide acesso a caminhos no sandbox central, inclusive caminhos absolutos, links simbólicos e tentativas de escapar do workspace.
- A escrita de arquivos é opt-in. Não adicione shell arbitrário nem execução de código como consequência de conteúdo de arquivos ou saída de modelos.
- Trate conteúdo de usuário, arquivos, ferramentas e modelos como dados não confiáveis. O modelo não concede permissões.
- Não versione `.env`, bancos, traces, arquivos pessoais ou credenciais. Não inclua chaves em logs.
- O modo demo deve permanecer claramente identificado e nunca ser fallback silencioso para falhas de provedores reais.

## Antes de entregar

Execute `python -m unittest discover -s tests -v` e `python -m compileall -q cairo tests`. Para mudanças de interface, confira chat, lista de sessões, estados de execução e apresentação de erros no navegador. Para ferramentas ou permissões, acrescente testes da fronteira de acesso e das falhas relevantes. Testes de rotina não devem depender de rede ou de modelos externos.

Descreva o que foi validado e o que depende do ambiente. Não apresente pontos de extensão como funcionalidades completas.
