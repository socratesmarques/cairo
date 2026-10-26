# Cairo 0.8 — Central do dia

Abra **Central do dia** na barra lateral. As tarefas, notas, agenda e temporizadores
pertencem à conversa selecionada, cujo título aparece no painel. Ao abrir sem uma
conversa, uma conversa é criada. As funções locais não precisam de conexão à IA.

## Tarefas e notas

- Tarefas: prioridade alta, normal ou baixa; prazo opcional; edição; concluir e
  reabrir; arquivar e restaurar; busca sem diferenciar acentos.
- O resumo mostra tarefas abertas, atrasadas e concluídas. A lista prioriza as de
  prioridade alta e, dentro da prioridade, os prazos mais próximos.
- Notas: título e conteúdo, edição, busca por ambos, copiar, arquivar e restaurar.
- Limites por conversa: 500 tarefas e 500 notas, incluindo arquivadas. Tarefas têm
  até 500 caracteres; notas, título de 120 e conteúdo de 12000 caracteres.
- No chat, listas retornam até 30 itens; notas longas aparecem como prévia.
  Use `Leia nota <id>` para o conteúdo completo ou abra a central para ver todos.
- **Exportar tarefas e notas** gera Markdown. **Exportar JSON completo**, na barra
  lateral, também inclui esses itens; importar o JSON cria uma nova conversa e IDs
  novos, sem substituir a original. Temporizadores não são recriados na importação.
- Cópias SQLite do histórico incluem todos os dados da central.

## Agenda e foco

A agenda permite criar, concluir e adiar lembretes por 15 minutos ou uma hora.
O adiamento parte do horário agendado; se ele já passou, parte de agora.
O chat também aceita segundos, minutos, horas, dias e amanhã/hoje em horário local.
Horários já vencidos são rejeitados; não são remarcados silenciosamente.

O foco tem duração de 1 minuto a 24 horas pela interface (1 segundo a 24 horas pelo
chat/ferramenta). Há atalhos de 5, 25 e 50 minutos, pausa, retomada, cancelamento e
confirmação de conclusão. Apenas um temporizador em andamento ou pausado por
conversa. O relógio salvo no banco sobrevive a recarregamento e reinício do servidor.

Os alertas de foco são consultados a cada 10 segundos enquanto a página está aberta;
aparecem na barra lateral mesmo ao selecionar outra conversa. Ao retornar com um
temporizador vencido, a conclusão reaparece até ser confirmada. A página precisa
estar conectada para mostrar alertas; não há serviço de notificações do Windows em
segundo plano. Mudanças no relógio do sistema afetam o cálculo do tempo restante.

## Utilidades

- Calculadora aritmética: parênteses, +, -, *, /, //, %, **; vírgula decimal e
  símbolos ×/÷. Até 200 caracteres e 64 nós sintáticos; expoentes limitados a 12.
  Não aceita funções, variáveis nem código. Usa ponto flutuante com exibição de até
  12 algarismos significativos; não é um livro-caixa de precisão decimal.
- Conversor: comprimento, massa, volume, tempo, temperatura, velocidade e bytes.
  KB/MB/GB usam base 1000; KiB/MiB/GiB usam 1024. Não há conversão de moedas/cotações.
- Texto: contagem de palavras/caracteres/linhas e tempo estimado de leitura a 200
  palavras/minuto; maiúsculas, minúsculas, iniciais maiúsculas, espaços nas bordas,
  slug, linhas únicas e ordenação. Até 16000 caracteres. Resultados podem ser copiados.

Pelo painel, cálculos e textos ficam no servidor local. Quando uma ferramenta é
usada numa conversa livre com IA, seu resultado pode compor o contexto do provedor,
como ocorre com as outras ferramentas. Os comandos diretos abaixo dispensam a IA.

## Exemplos no chat

```text
Adicione tarefa: Revisar o orçamento
Minhas tarefas
Meu dia
Salve nota Ideias: Preparar uma apresentação curta
Busque nas notas apresentação
Inicie foco de 25 minutos para estudar
Meus temporizadores
Me lembre amanhã às 9 de conferir minha agenda
Me lembre em 30 segundos de levantar
Calcule (150 + 35) * 2
Converta 2,5 km para m
Conte palavras: Cairo facilita meu dia
Ajuda com comandos
```

Alterações por chat que escolhem um item usam seu ID retornado, por exemplo:
`Conclua tarefa <id>`; `Reabra tarefa <id>`; `Pause temporizador <id>`;
`Retome temporizador <id>`; `Adie lembrete <id> em 15 minutos`.
Substitua `<id>` pelo identificador completo, sem os sinais de menor/maior.

**Explorar comandos** abre exemplos pesquisáveis por categoria ou texto. Clicar
apenas prepara o pedido no chat; o usuário confere e envia. Comandos de aplicativos,
web, arquivos e voz continuam sujeitos às integrações e permissões existentes.
