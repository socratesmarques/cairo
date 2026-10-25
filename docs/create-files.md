# Criar arquivos fora da workspace

Com `CAIRO_FULL_FILE_ACCESS=true` e `CAIRO_ALLOW_FILE_OPERATIONS=true`, Cairo aceita
caminhos absolutos em unidades locais ou montadas, sujeitos às permissões Windows.
`CAIRO_ALLOW_WRITE=true` habilita também a ferramenta antiga de escrita.
A instalação em Documentos já possui essas opções habilitadas.

Exemplos no chat, inclusive em modo demo:

```text
Crie o arquivo "C:\Users\Usuario\Documents\anotacoes.txt"
Crie o arquivo "C:\Users\Usuario\Downloads\teste.txt" com texto "Olá, Cairo!"
Crie a pasta "C:\Users\Usuario\Documents\Meus Projetos\Novo"
```

As pastas intermediárias são criadas quando necessário. O primeiro exemplo cria um
arquivo vazio. O conteúdo pode incluir aspas e quebras de linha entre as aspas externas.
Pedidos livres como “crie um script Python em Downloads” usam o modelo configurado;
formas diretas acima não precisam de modelo. Texto, código, JSON, CSV, HTML e outros
formatos textuais são gravados em UTF-8, até 64 KiB por criação. Escrever texto com
extensão `.docx`, `.pdf` ou `.xlsx` não gera um documento válido nesses formatos.

Arquivos existentes não são sobrescritos na criação. Para alterações, use o fluxo
de edição com backup. Não há elevação automática de administrador. Arquivos internos
do Cairo, armazenamento, caminhos de dispositivo/UNC, links e nomes reservados
continuam protegidos. O Cairo só anuncia sucesso depois que a gravação conclui.

Para ferramentas, use `file_write_text(path, content, create_parents=True)` e
`file_mkdir(path, parents=True)`. O modo de acesso e o pedido atual do usuário são
validados pelo registro central. Saídas de páginas ou modelos não concedem escrita.
