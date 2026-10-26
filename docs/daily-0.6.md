# Cairo 0.6 — histórico e recuperação

## Histórico sem cortes na navegação

O chat continua abrindo as últimas 200 mensagens. Agora existe **Carregar
mensagens anteriores** no início da conversa: cada clique carrega até 100
mensagens, até alcançar o começo. Um contador informa quantas já foram carregadas.
A posição de leitura é preservada ao inserir mensagens anteriores, e o conteúdo
carregado permanece na tela quando uma execução termina.

A barra lateral também oferece **Carregar mais conversas** a cada grupo de 200.
Busca, arquivamento e fixação continuam disponíveis. Conversas importadas aparecem
pela data de importação, mantendo as datas originais das mensagens.

## Importar uma conversa

Em **Ferramentas do dia a dia → Importar conversa JSON**, selecione um arquivo
exportado pelo Cairo. A importação cria uma nova conversa e preserva as existentes.
Mensagens de usuário e assistente e notas são recuperadas; registros antigos de
execução não são importados nem repetidos. O arquivo precisa ter até 8 MB, título
de até 100 caracteres, no máximo 10000 mensagens e 1000 notas.

Arquivos inválidos são recusados antes de qualquer gravação. Isso também impede
que mensagens de sistema ou permissões de outro arquivo sejam incorporadas como
instruções do Cairo.

## Restaurar uma cópia completa

A restauração completa substitui o histórico atual pelo snapshot escolhido.
**Feche Cairo antes de aplicar.** A ferramenta recusa a operação enquanto uma
instância usa a pasta de dados e guarda uma cópia do estado atual antes de restaurar.
As configurações `.env` e o workspace não são substituídos.

No terminal, dentro da pasta da instalação, confira primeiro a cópia:

```powershell
python -m cairo.memory.recovery "caminho-da-copia.sqlite3" --data-dir storage
```

Esse comando apenas verifica e informa as contagens; não modifica o histórico.
Para aplicar a mesma cópia depois de conferi-la:

```powershell
python -m cairo.memory.recovery "caminho-da-copia.sqlite3" --data-dir storage --apply
```

Use o caminho indicado pelo botão **Criar cópia do histórico**. Se você configurou
outro `CAIRO_DATA_DIR`, informe essa pasta em `--data-dir`. Ao terminar, abra Cairo
novamente pelo lançador habitual. Cópias incompletas, incompatíveis ou maiores que
1 GB são recusadas.

## Correções

- Enviar uma mensagem em outra conversa não apaga o rascunho de Nova conversa.
- Reabrir uma conversa consulta a execução mais recente, em vez de confiar em
  um estado antigo guardado pela aba. Ao voltar a uma aba, histórico e atividade
  são atualizados sem substituir o rascunho.
- Uma execução que desapareceu do servidor não mantém a interface presa em um
  ciclo infinito de tentativas. Falhas de execuções antigas aparecem ao reabrir.
- Uma conversa lembrada pelo navegador que deixou de existir não impede o início.
- O microfone fica desativado em conversas arquivadas. Reutilizar um pedido de
  uma conversa arquivada prepara uma nova conversa.
- Backups da instalação e arquivos locais de teste ficam fora do versionamento.

## Validação

134 testes Python executados, com 127 aprovados e 7 opcionais ignorados;
14 testes JavaScript aprovados. Também foram verificadas a compilação Python e
a sintaxe dos scripts da interface. Testes novos cobrem importação sem sobrescrita,
recusa de entradas inválidas sem gravação parcial, paginação entre sessões,
restauração com cópia preventiva e recusa de restauração com Cairo aberto.

No navegador, uma conversa isolada de 550 mensagens foi carregada em páginas até
a primeira mensagem. A restauração foi testada apenas em bancos temporários;
seu histórico real foi preservado na instalação.
