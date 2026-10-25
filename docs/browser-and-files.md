# JavaScript e operações de arquivos

Atualização: o modo de acesso por caminho absoluto, a descoberta de aplicativos e a leitura Google estão descritos em [expanded-access.md](expanded-access.md). Quando `CAIRO_FULL_FILE_ACCESS=true`, o acesso deixa de exigir cadastro de cada pasta; as demais verificações e limites continuam valendo.

## Navegação com JavaScript

`read_webpage` passa a renderizar a página quando `CAIRO_BROWSER_JAVASCRIPT=true`. A ferramenta `read_dynamic_webpage` também permite aguardar um elemento CSS específico. Exemplos: `Leia https://quotes.toscrape.com/js/` ou `Resuma https://example.com`. O primeiro é um comando direto; o resumo usa o modelo para ler a fonte e sintetizar a resposta.

Usamos [Playwright para Python](https://playwright.dev/python/docs/library), em um Chrome headless com contexto anônimo novo a cada leitura. O runtime principal continua sem dependências obrigatórias; Playwright está no extra `browser`, necessário apenas para este recurso. A configuração instalada usa o Chrome existente:

```dotenv
CAIRO_BROWSER_JAVASCRIPT=true
CAIRO_BROWSER_CHANNEL=chrome
CAIRO_ALLOW_NETWORK=true
```

Na pasta Cairo, a instalação reproduzível é:

```powershell
python -m pip install -e ".[browser]"
```

`CAIRO_BROWSER_CHANNEL` aceita `chrome`, `msedge` ou `chromium`. O último precisa do binário correspondente, instalado com `python -m playwright install chromium`. Consulte a [documentação dos navegadores](https://playwright.dev/python/docs/browsers).

A leitura devolve título, texto visível, URL final e até 40 links, depois da execução de JavaScript. Cookies, armazenamento e sessão são descartados ao fechar o contexto; não são usados os logins do seu Chrome pessoal. Não há ferramenta para executar JavaScript arbitrário escolhido pelo modelo no computador. Este recurso executa os scripts da página dentro do navegador, para renderizar sites.

Requisições da página são interceptadas e transferidas pelo cliente HTTPS com IP público validado e fixado na conexão TLS; a validação do certificado usa o hostname original. Isso também se aplica a scripts, XHR e redirecionamentos. Aceitamos GET/HEAD/POST com corpo de até 256 KB para APIs dinâmicas. HTTP local/privado, métodos destrutivos, WebSockets, service workers, downloads, novas janelas e mídia/fontes/imagens são bloqueados. O navegador não recebe acesso aos arquivos pessoais do Cairo. O leitor não é um sandbox de código hostil de propósito geral; mantenha Chrome e Playwright atualizados.

Limites: duas leituras simultâneas, até 100 requisições, 2 MiB por recurso, 12 MiB por página e 12 mil caracteres extraídos. A leitura aguarda carregamento/atividade de rede por um intervalo limitado, com prazo de renderização de 45 segundos e fechamento ao terminar. O encerramento de uma transferência já em andamento pode levar o timeout de rede adicional. Páginas que exigem login, CAPTCHA, long polling/WebSocket, arquivos maiores ou recursos bloqueados podem não funcionar completamente; não há tentativa de contornar essas restrições.

## Manipular arquivos do computador

```dotenv
CAIRO_ALLOW_FILE_OPERATIONS=true
CAIRO_FILE_ROOTS={}
```

As pastas disponíveis são `workspace`, `downloads`, `documents`, `desktop`, `pictures`, `music` e `videos`. Os caminhos pessoais são obtidos pelo Windows, inclusive redirecionamentos para OneDrive. Você pode cadastrar outras pastas explicitamente no ambiente, por exemplo:

```dotenv
CAIRO_FILE_ROOTS={"projetos":"D:/Projetos"}
```

O programa aceita `alias/caminho` e caminhos absolutos dentro dessas pastas. Não aceita uma unidade inteira como pasta extra. Alterações nessa configuração exigem reinício.

### Comandos diretos, sem depender do modelo

```text
Liste as pastas cadastradas
Crie uma pasta "downloads/Organizado"
Crie um arquivo "documents/notas.txt" com texto "Lembrar de estudar"
Copie "downloads/Relatório.pdf" para "documents/Relatório.pdf"
Mova "downloads/arquivo.zip" para "downloads/Organizado/arquivo.zip"
Renomeie "documents/notas.txt" para "minhas-notas.txt"
Edite "documents/minhas-notas.txt" substituindo "estudar" por "revisar"
Busque "Relatório" em "documents"
Informações do arquivo "documents/Relatório.pdf"
Hash "documents/Relatório.pdf"
Apague "downloads/arquivo-teste.txt"
Liste a lixeira
Restaure CODIGO_RETORNADO_PELO_CAIRO
```

Nos comandos diretos, use aspas duplas nos caminhos para preservar espaços, caixa e acentos. O código da lixeira contém 32 caracteres hexadecimais, sem aspas. Os mesmos recursos ficam disponíveis ao modelo nos pedidos naturais. Para abrir a lista de permissões e limites atuais, diga `O que você pode fazer?`.

### Regras das operações

- Copiar, mover, renomear e calcular hash funcionam para qualquer formato de arquivo até 256 MiB, inclusive PDF, imagem, vídeo ou ZIP. Isso não significa que Cairo interpreta o conteúdo desses formatos.
- Destinos existentes não são sobrescritos por cópia, movimentação, renomeação, criação ou restauração da lixeira. A pasta de destino precisa existir.
- Edição é uma substituição exata que deve ocorrer uma única vez em texto UTF-8 de até 64 KiB. Antes de alterar, guarda o original e retorna um código de recuperação. Mudanças posteriores no arquivo impedem restauração automática para não perdê-las.
- Apagar envia um arquivo à lixeira **do Cairo**, em `storage/file-trash`, com cópia verificada por SHA-256 antes de remover a origem. Não é a Lixeira do Windows. Não há exclusão permanente, limpeza automática da lixeira ou exclusão/movimentação recursiva de pastas.
- Backups e lixeira são vinculados à conversa que executou a ação. `Liste a lixeira` mostra até 100 registros dessa conversa, incluindo backups de edições e operações interrompidas. Dados permanecem em disco até uma manutenção explícita; considere o espaço usado.
- `file_search` busca nomes, com até 5 mil entradas examinadas e 100 resultados. `file_info` informa tamanho e alteração; `file_hash` calcula SHA-256.
- Caminhos não podem escapar das raízes, atravessar links/junções, usar streams NTFS ou nomes reservados. O código/configuração internos do Cairo e sua pasta de dados são protegidos. A subpasta workspace permanece disponível para trabalho.
- Conteúdo de páginas, notas e arquivos não autoriza alterações. O orquestrador habilita ferramentas de alteração somente quando o pedido atual do usuário contém uma ação explícita, como copiar, mover, criar, editar, organizar, apagar ou restaurar. Um pedido somente de leitura mantém alterações bloqueadas, mesmo se o modelo tentar chamar essas ferramentas.
- Operações em uma mesma instância são serializadas. As verificações protegem contra caminhos escolhidos pelo modelo; um processo local hostil trocando diretórios em paralelo requer isolamento do sistema operacional, que este aplicativo não fornece. Cancelar uma execução aguarda a operação de arquivo em andamento.

`CAIRO_ALLOW_PERSONAL_FILES` continua controlando as ferramentas antigas de leitura/listagem pessoal; `CAIRO_ALLOW_FILE_OPERATIONS` controla o novo gerenciador. `CAIRO_ALLOW_WRITE` continua controlando as ferramentas antigas de escrita no workspace. Nenhuma dessas permissões é concedida por texto retornado pelo modelo.

## Verificação

```powershell
python -m unittest discover -s tests -v
python -m compileall -q cairo tests
node --test tests/test_voice.cjs
```

Para testar o Chrome real com JavaScript e isolamento de cookies, sem depender da internet:

```powershell
$env:CAIRO_TEST_BROWSER='1'
python -m unittest discover -s tests -p test_browser_reader.py -v
```

O teste serve uma página simulada pelo interceptador da rede e verifica texto produzido por JavaScript, além de contextos sem compartilhamento de cookies. Os testes de arquivos usam temporários, incluindo destinos existentes, restauração, backup de edição, autorização, raiz protegida e bloqueio de traversal. A validação manual adicional lê um site público com JavaScript e executa o ciclo de arquivos em uma subpasta de teste, sem modificar documentos existentes.
