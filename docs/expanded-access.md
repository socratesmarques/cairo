# Arquivos fora do workspace, Google e aplicativos instalados

As três opções são independentes. Nesta instalação foram ativadas no `.env` por solicitação do usuário:

```dotenv
CAIRO_FULL_FILE_ACCESS=true
CAIRO_DISCOVER_APPS=true
CAIRO_GOOGLE_SEARCH_READ=true
```

As permissões anteriores continuam valendo: `CAIRO_ALLOW_FILE_OPERATIONS=true`, `CAIRO_ALLOW_DESKTOP=true` e `CAIRO_ALLOW_NETWORK=true` habilitam suas respectivas ferramentas. Playwright e o canal escolhido em `CAIRO_BROWSER_CHANNEL` são necessários para a pesquisa Google.

## Arquivos por caminho absoluto

Com `CAIRO_FULL_FILE_ACCESS=true`, as ferramentas do gerenciador aceitam caminhos absolutos de unidades locais ou montadas, além de aliases. Não é preciso cadastrar cada pasta em `CAIRO_FILE_ROOTS`. A lista de raízes inclui as unidades disponíveis (`drive_c`, `drive_d`, etc.). Exemplos:

```text
Leia o arquivo "D:/Projetos/notas.txt"
Liste os arquivos em "C:/Users/Usuario/AppData/Local/MinhaPasta"
Abra a pasta "D:/Projetos"
Copie "D:/Projetos/notas.txt" para "documents/notas.txt"
Busque "relatorio" em "D:/Trabalho"
```

Use aspas nos comandos diretos. A leitura de conteúdo é texto UTF-8 até 64 KiB; listagem, metadados, busca e operações de arquivos seguem os limites anteriores. Copiar/mover/renomear/lixeira aceitam formatos binários até 256 MiB. Não é uma conversão automática de PDF/Word/imagens para texto.

O processo segue as permissões da conta do Windows. Cairo não se eleva, não altera ACLs e não contorna arquivos bloqueados. Caminhos UNC/de dispositivo, links/junções, streams NTFS e traversal continuam bloqueados. A leitura por caminho absoluto pode acessar arquivos internos do próprio Cairo; a escrita/movimentação/lixeira de código, configuração interna e armazenamento do Cairo continua protegida, com exceção do workspace. Alterações continuam exigindo uma intenção explícita na mensagem atual do usuário. Restauração e backup seguem [browser-and-files.md](browser-and-files.md).

## Leitura dos resultados do Google

```text
Pesquise documentação Python no Google
```

Quando `CAIRO_GOOGLE_SEARCH_READ=true`, `search_web` lê resultados em vez de apenas abrir uma URL. A ferramenta `google_search` fornece a mesma capacidade ao Master, ResearchAgent e SystemAgent. Retorna até cinco títulos, URLs e trechos extraídos da página real; links de navegação e duplicatas são descartados. Ler os resultados não significa ler integralmente os sites encontrados: o modelo pode usar `read_webpage` no link relevante para aprofundar a resposta.

A pesquisa usa uma janela visível com perfil próprio em `storage/google-profile`, separado do Chrome pessoal. O perfil persiste para manter escolhas de privacidade e verificações do Google. Não é necessário entrar em uma conta. O serviço e o navegador são mantidos em uma thread única e fechados ao encerrar Cairo. Há uma pesquisa por vez. A janela só navega para domínios do Google, conteúdo estático e verificação associados; links externos podem ser lidos pela ferramenta web ou abertos no navegador habitual. Diferentemente do leitor geral de páginas com transporte HTTPS fixado, a pesquisa usa a conexão nativa do Chrome, restrita a esses domínios e com resolução pública verificada.

Estados retornados:

- `ok`: resultados extraídos, com títulos/links/trechos.
- `verification_required`: o Google pediu verificação humana. Conclua na janela aberta e repita a pesquisa. Nenhum resultado é inventado.
- `consent_required`: escolha de privacidade precisa ser feita na janela; depois repita a pesquisa.
- `no_results`: o Google indicou explicitamente que não encontrou resultados.
- `unavailable`: o formato não pôde ser lido ou a página exige outra interação.

O teste real nesta rede recebeu `verification_required` por tráfego incomum. A extração de resultados foi validada em fixtures HTML e em um DOM real do Chrome; a consulta ao Google ao vivo ainda depende da verificação humana. Não há solução automática de CAPTCHA, proxies de evasão, alteração de fingerprint ou substituição silenciosa por outro buscador.

## Abrir aplicativos instalados

```text
Liste os aplicativos
Abra Firefox
Abra Paint
Abra Cursor
Abra "C:/Programas/MeuAplicativo/MeuAplicativo.exe"
```

Com a descoberta habilitada, a abertura deixa de depender da lista fixa em `desktop.json`. Consultamos o [menu Iniciar via Get-StartApps](https://learn.microsoft.com/en-us/powershell/module/startlayout/get-startapps) e as chaves [App Paths do Windows](https://learn.microsoft.com/en-us/windows/win32/shell/app-registration). O catálogo é mantido em cache por 60 segundos. Esta máquina apresentou 339 entradas na validação, incluindo programas Win32 e aplicativos da Store.

`desktop_apps` devolve até 200 entradas por consulta, com `total`, `truncated`, `warnings` e filtro opcional `query`. O agente pode filtrar pelo nome e usar o ID retornado. Nomes ambíguos produzem opções; um programa não encontrado não é considerado aberto. Executáveis portáteis podem ser abertos pelo caminho absoluto `.exe` existente, sem necessidade de registro. Aplicativos não instalados, sem registro/caminho conhecido ou incompatíveis com a sessão atual não podem ser garantidos.

A abertura usa o executável com lista de argumentos vazia ou o AppID obtido do próprio Windows via Explorer/AppsFolder. A mensagem não vira uma linha de comando. Não aceitamos argumentos como `powershell -Command ...` dentro do nome do aplicativo. Abrir PowerShell/Terminal explicitamente é permitido como abertura de programa, sem executar comandos. O orquestrador bloqueia `open_app` em pedidos somente de leitura, mesmo se o modelo tentar chamar essa ferramenta.

Retorno de sucesso significa solicitação de abertura enviada. O programa ainda pode pedir UAC, ter uma falha própria ou não criar janela; Cairo não afirma verificação visual. Os controles de janelas anteriores continuam voltados aos aplicativos do catálogo original, não a qualquer programa da Store.

## Testes

```powershell
python -m unittest discover -s tests -v
python -m compileall -q cairo tests
node --test tests/test_voice.cjs
$env:CAIRO_TEST_BROWSER='1'
python -m unittest discover -s tests -p test_browser_reader.py -v
```

Os testes novos cobrem caminhos absolutos, proteção de escrita interna, leitura e listagem fora do workspace, catálogo/cache, launch sem shell, ambiguidade de nomes, intenção explícita de abertura, limpeza dos resultados Google e status de verificação. O teste opcional do navegador executa a extração em HTML controlado. Os testes padrão não dependem do Google nem abrem aplicativos reais.
