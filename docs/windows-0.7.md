# Posicionamento geral de aplicativos — Cairo 0.7

O posicionamento deixou de depender apenas do catálogo fixo. Com a descoberta de
aplicativos já habilitada na instalação, os mesmos comandos funcionam com os nomes
do menu Iniciar, IDs de aplicativos instalados, executáveis locais e IDs de janelas.
Aplicativos tradicionais, Electron e aplicativos empacotados da Microsoft Store
são identificados pelo Windows; o Cairo não escolhe janelas apenas pelo título.

## Comandos

```text
Abra YouTube Music Desktop e coloque pra cima
Abra Firefox e coloque na esquerda
Mova Visual Studio Code para baixo
Coloque o Chrome no canto superior direito
Mova YouTube Music Desktop para o canto inferior esquerdo
Centralize o Chrome
Abra Calculadora na direita
```

"Abra" inicia o aplicativo e aguarda a janela. "Mova", "coloque" e "posicione"
agem sobre uma janela existente. Se o aplicativo possui várias janelas, é usada a
que está em primeiro plano; se nenhuma delas estiver em primeiro plano, a primeira
na ordem de sobreposição do Windows. Para escolher uma janela específica, use:

```text
Liste as janelas
Mova a janela win:123:456 para cima
```

Troque `win:123:456` pelo ID realmente retornado. O processo também é validado
para evitar usar um identificador de janela que foi reciclado pelo Windows.

## Posições e monitores

Direita, esquerda, cima e baixo usam metade da área útil. Os quatro cantos usam
um quarto. Centro preserva o tamanho atual quando ele cabe no monitor.
"Tela inteira" neste comando corresponde a maximizar a janela.

```text
Liste os monitores
Mova Firefox para o canto superior direito no monitor 2
Abra Visual Studio Code na esquerda no monitor principal
```

O monitor 1 é o principal. Os demais são ordenados pela posição na configuração
atual do Windows. Sem monitor explícito, é usado o monitor da janela.
A área útil respeita a barra de tarefas, monitores com origem negativa e escala DPI.

## Coordenadas e tamanho personalizados

```text
Posicione Chrome em x 100 y 80 com largura 900 e altura 600
Mova Chrome para a posição 100, 80 com tamanho 900x600
Posicione Chrome em x 25% y 10% com largura 50% e altura 60%
```

Pixels são coordenadas absolutas da área de trabalho do Windows. Nessa modalidade,
o monitor é escolhido pela coordenada inicial, salvo quando você especifica um.
Porcentagens são relativas à área útil do monitor escolhido, ou ao monitor atual
da janela. Se omitir largura e altura, o tamanho atual é preservado.
Coordenadas e dimensões precisam caber no monitor; uma entrada inválida não é
transformada silenciosamente em outra posição.

## Restrições reais de aplicativos

O Cairo mede a posição depois de mover. Se o aplicativo impuser um tamanho mínimo,
é tentado um encaixe na mesma borda/canto e a resposta informa o ajuste. Se a janela
recusar o movimento ou não couber no monitor, o erro é exibido e é tentada a
restauração da posição anterior. Não há promessa de sucesso para janelas protegidas,
aplicativos elevados, interfaces sem janela normal ou modos que bloqueiam
redimensionamento. A escuta contínua permanece ativa após esses erros de execução.

Nomes ambíguos de aplicativos precisam ser especificados pelo nome completo ou ID.
O catálogo pode ser consultado com "Liste os aplicativos". Sem descoberta habilitada,
continuam disponíveis os aplicativos cadastrados e os IDs explícitos de janelas.
