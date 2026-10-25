# Aplicativos, terminal e navegador com JavaScript

## Ativar

No Windows, dentro da pasta Cairo:

```powershell
python -m pip install -e ".[browser,desktop]"
```

Use Chrome instalado e configure `.env`:

```dotenv
CAIRO_ALLOW_DESKTOP=true
CAIRO_DISCOVER_APPS=true
CAIRO_ALLOW_APP_CONTROL=true
CAIRO_ALLOW_COMMANDS=true
CAIRO_COMMAND_TIMEOUT=30
CAIRO_ALLOW_NETWORK=true
CAIRO_BROWSER_AUTOMATION=true
CAIRO_BROWSER_CHANNEL=chrome
```

Encerre o Cairo anterior com Ctrl+C antes de iniciar `python -m cairo.desktop`.
Não abra outra instância usando a mesma pasta de dados.

## Exemplos no chat

- `Abra o Bloco de Notas` ou `Abra o Google Chrome`.
- `Liste as janelas` e `Inspecione janela win:123:456` (use um ID real retornado).
- `Abra o Bloco de Notas e digite Olá, Cairo no campo de texto`.
- `Clique no botão Aplicar da janela de configurações`.
- `Minimize janela win:123:456` ou `Restaure janela win:123:456`.
- `Execute no CMD: dir`.
- `Execute no PowerShell: Get-Date`.
- `Execute no CMD em "C:\Users\Usuario\Downloads": dir`.
- `Abra no navegador Cairo https://example.com`.
- `Leia a pagina atual`.
- `Preencha o campo de pesquisa da página com Cairo e clique em Pesquisar`.

Comandos explícitos de abertura, listagem, IDs e terminal funcionam sem modelo.
Pedidos em linguagem natural com vários passos precisam de um modelo que suporte
chamadas de ferramentas. O agente inspeciona a janela/página e usa os IDs encontrados.
IDs de controles expiram após dois minutos; elementos do navegador mudam a cada leitura.
É possível usar diretamente `Clique no controle ctl:...`, `Preencha ctl:... com "texto"`,
`Clique no elemento dom:...` e `Preencha dom:... com "texto"` com IDs válidos.

## Funcionamento

O registro de ferramentas permanece a única entrada dos agentes. O controle Windows
usa UI Automation em um processo auxiliar persistente, com comunicação JSON e limite
de tempo; falhas do provedor de acessibilidade não derrubam o chat. O processo é
encerrado no fechamento do Cairo. Não são instalados serviços nem drivers.

CMD e Windows PowerShell executam somente o comando literal depois do prefixo
`Execute no CMD:` ou `Execute no PowerShell:`. O modelo não pode substituir o comando.
Há limite de concorrência, saída e tempo (1 a 300 segundos), código de saída e botão
de cancelamento do chat. Um Windows Job Object encerra os processos filhos ao terminar.
O ambiente dos filhos omite variáveis CAIRO/FCC/OpenAI/Anthropic.

**Comandos executam com os direitos da sua conta Windows. Não são uma sandbox de
segurança:** podem alterar arquivos e configurações fora das raízes das ferramentas
de arquivos. Não há elevação automática nem desvio de UAC. Saída de comandos entra
no histórico; evite executar comandos que imprimem credenciais.

O navegador mantém uma página isolada por conversa (até três conversas ativas),
executa o JavaScript do site e permite ler, clicar, preencher, selecionar, rolar e
aguardar elementos. A rede aceita páginas públicas HTTPS, valida os destinos e limita
requisições/volume. Cookies pessoais do seu Chrome não são importados. Fechar Cairo
descarta esses contextos. O resultado de uma ação deve ser conferido por nova leitura.

## Limites

Aplicativos devem expor controles acessíveis. Jogos, canvas, algumas interfaces
personalizadas, janelas elevadas, desktop bloqueado e diálogos protegidos podem não
funcionar. Não existe reconhecimento visual universal de qualquer aplicativo.
O Cairo não confirma automaticamente diálogos de salvar ao fechar uma janela.

O navegador não contorna login, CAPTCHA ou proteção de sites; downloads, popups,
WebSockets e service workers estão desativados. Não oferece um console para executar
JavaScript arbitrário no computador. JavaScript das páginas funciona no Chrome;
programas Node podem ser executados pelo terminal se Node estiver instalado.
Envios de mensagens, compras e formulários exigem pedido explícito no turno atual.

## Validação

```powershell
python -m unittest discover -s tests -v
$env:CAIRO_TEST_BROWSER='1'
$env:CAIRO_TEST_DESKTOP='1'
python -m unittest discover -s tests -p test_control_features.py -v
```

Os testes opcionais usam uma janela nativa própria e HTML controlado com JavaScript,
sem alterar documentos abertos. O teste FCC continua opcional e independente.
