# Abrir arquivos no Windows

Para escolher o editor: `Abra o arquivo "C:\Users\Usuario\Documents\teste.py" no VS Code`.
Também funciona `Abra no VS Code o arquivo "C:\Users\Usuario\Documents\teste.py"`.
O registro de ferramentas aceita `open_file(path=..., app="VS Code")` ou o ID instalado.
O arquivo é enviado como argumento separado ao executável, sem interpretar shell.
Aplicativos Store sem executável não recebem esse argumento; use a associação padrão.

Pedidos compostos como “crie o arquivo e abra no VS Code” e formas de fala como
“nesse novo arquivo abre o Visual Studio” são reconhecidos. Referências ao arquivo
usam o histórico e precisam de um modelo com ferramentas; caminhos explícitos nas
formas acima funcionam sem modelo. Textos citados e instruções de páginas não
concedem autorização. Perguntas como “por que não abriu?” não abrem aplicativos sozinhas.

Use `Abra o arquivo "C:\Users\Usuario\Downloads\relatorio.pdf"` ou
`Abra o arquivo "documents/anotacoes.txt"` no chat. Comandos nessas formas passam
diretamente pela ferramenta `open_file`, inclusive sem modelo e em modo swarm.
Pedidos livres usam o modelo para localizar o caminho e chamar a mesma ferramenta.

Não há lista de extensões permitidas: Windows abre o arquivo com a associação padrão,
sem transformar o caminho em comando de terminal. PDF, Word, Excel, imagens, áudio e
outros formatos dependem dos aplicativos instalados e associados. Abrir um script ou
executável pode executar código conforme sua associação no Windows; a ação só é
oferecida quando o usuário solicita abertura no turno atual. Conteúdo de documentos,
notas e páginas não autoriza abertura.

`CAIRO_ALLOW_DESKTOP=true` permite a abertura e `CAIRO_FULL_FILE_ACCESS=true` permite
caminhos absolutos externos. Ambas já estão habilitadas nesta instalação. A ferramenta
usa as mesmas regras centrais de caminhos e as permissões da conta Windows. Ela não
altera ACLs, antivírus, SmartScreen, UAC ou políticas administrativas.

Erros distinguem arquivo inexistente, pasta em vez de arquivo, falta de associação,
acesso negado, cancelamento e bloqueio por política. Cairo confirma o envio da
solicitação ao aplicativo, não o carregamento visual do documento. Abrir um PDF em um
leitor não significa que Cairo extraiu ou compreendeu seu conteúdo.
