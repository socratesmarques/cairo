# Cairo 0.5 — uso diário

Abra Cairo pelo lançador existente **Abrir Cairo.cmd**. A instalação em
`C:\Users\Usuario\Documents\Cairo` conserva o `.env`, os dados e o workspace.
Se uma instância anterior estiver aberta, encerre-a e abra novamente.

## Conversas organizadas

- **Busca:** pesquisa título e mensagens, sem diferenciar maiúsculas ou acentos.
  `Ctrl+K` (ou `Cmd+K`) leva à busca. Cada consulta lista até 200 conversas.
- **Fixar:** use a estrela junto ao título. Conversas fixadas aparecem primeiro;
  as demais são ordenadas pela atividade mais recente.
- **Renomear:** título de até 100 caracteres, salvo no histórico local.
- **Arquivar:** guarda a conversa na aba Arquivadas, com opção Restaurar.
  As mensagens permanecem intactas. Não é possível arquivar uma execução ativa.
- **Rascunhos:** cada conversa e a tela Nova conversa têm seu próprio rascunho.
  O navegador recupera o texto ao trocar de conversa ou recarregar a página.
  Esse texto fica no perfil local do navegador; não sincroniza entre aparelhos.

## Escrita e leitura

O botão de tema alterna entre claro e escuro e memoriza sua escolha no navegador.
As respostas exibem títulos, negrito, listas, citações, tabelas e blocos de código
com botão Copiar código. É um subconjunto de Markdown; HTML é exibido como texto.
Links reconhecidos usam apenas HTTP/HTTPS e abrem sem acesso à aba de origem.

A caixa de mensagem cresce com o texto. As opções de escuta contínua ficam em
Voz e escuta contínua. Enter envia e Shift+Enter insere uma linha. O ditado
continua dependendo da disponibilidade e das permissões do navegador.

Em telas menores, o menu de conversas abre pelo botão no cabeçalho. A equipe
fica em um painel separado. Escape fecha os painéis abertos.

## Exportação e cópias

Em Ferramentas do dia a dia:

- **Exportar JSON completo:** todas as mensagens, notas e execuções da conversa.
- **Exportar Markdown:** todas as mensagens de usuário e assistente, para leitura.
- **Criar cópia do histórico:** snapshot consistente de todo o banco SQLite,
  incluindo conversas, notas, lembretes e execuções. O arquivo é verificado e salvo
  em `storage/backups`, ou na subpasta `backups` do `CAIRO_DATA_DIR` configurado.
  A interface informa o caminho exato. O `.env` e arquivos pessoais não fazem parte
  desse snapshot. As cópias são mantidas até você as remover.

A tela de chat carrega as últimas 200 mensagens para manter a navegação leve;
uma indicação informa quando existe conteúdo anterior. As exportações incluem
todo o histórico, independentemente desse limite.

Na primeira abertura da versão 0.5, o banco existente ganha os campos de fixação
e arquivamento sem apagar registros. Se já houver conversas, uma cópia do banco
é feita antes dessa migração. A migração pode ser repetida sem duplicar colunas.

## Validação desta versão

- Suíte Python: 127 testes executados, 120 aprovados e 7 opcionais ignorados.
- Suíte JavaScript: 14 testes aprovados de conexão, ditado e escuta contínua.
- Compilação Python e verificação de sintaxe do JavaScript.
- No navegador: renomeação, arquivar/restaurar, recuperação de rascunho após
  recarga, tema claro, renderização de tabelas/código e execução multiagente
  com provedor demo em ambiente separado dos seus dados.
- Provedor FCC configurado: catálogo acessível e uma resposta real recebida
  com sucesso, sem ferramentas nem dados pessoais na solicitação de teste.

Os testes opcionais de integração com Chrome e janelas nativas não foram
executados nesta rodada. Conversas com modelos reais dependem do provedor
configurado estar acessível; o modo demo não substitui essa verificação.
