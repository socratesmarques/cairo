# Comandos compostos e escuta — 0.6.1

Pedidos reconhecidos diretamente, sem depender de interpretação do modelo:

```text
Abra YouTube Music Desktop e toque a música Nuts
Toque Nuts no YouTube Music Desktop
Abra o Visual Studio Code e colocar na direita
Abra VS Code e coloque na esquerda
```

A música é pesquisada em metadados públicos do YouTube e encaminhada ao
aplicativo pelo protocolo registrado `ytmd://play/<Video_Id>`,
[documentado pelo YTMDesktop](https://github.com/ytmdesktop/ytmdesktop/wiki/URI).
A seleção favorece o título solicitado e evita versões extended/remix/cover
quando isso não foi pedido. Você pode informar o artista para refinar a pesquisa.
É necessário ter conexão, o cliente desktop instalado e a sessão do YouTube
pronta para reproduzir. Cairo informa que enviou o pedido; não afirma ter
confirmado a reprodução no aplicativo. Não substitui silenciosamente o pedido
desktop por reprodução no navegador.

Ao abrir e posicionar um aplicativo, Cairo aguarda sua janela por até oito segundos.
A divisão usa a área útil do monitor da janela, respeitando a barra de tarefas e
monitores com origem negativa. A posição resultante é verificada antes da resposta.
O posicionamento nominal permanece limitado aos aplicativos do catálogo existente.

Na escuta contínua, uma execução que falha — inclusive aplicativo não encontrado —
mostra o erro e libera o próximo comando sem desligar a escuta. Cancelamento
manual, troca de conversa, bloqueio de microfone e falhas de reconhecimento mantêm
o comportamento de interrupção existente. Falha no envio cuja aceitação é incerta
também interrompe a escuta para evitar repetir ações sem saber o resultado anterior.

## Validação

139 testes Python executados: 132 aprovados e 7 opcionais ignorados. Outros
15 testes JavaScript foram aprovados, incluindo a recuperação da escuta após
aplicativo inexistente. Compilação Python e sintaxe JavaScript conferidas.

Na instalação real, os dois pedidos originais foram enviados pela interface:
a posição à direita do VS Code foi verificada pelo Windows e o URI de reprodução
do áudio oficial de Nuts foi encaminhado ao aplicativo desktop. O áudio tocando
no aplicativo não foi verificado automaticamente.
