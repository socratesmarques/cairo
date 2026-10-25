# Validação da V1

Verificação realizada em 23/10/2026 no Windows, com Python 3.14.6.

- 29 testes automatizados passaram, incluindo API HTTP de ponta a ponta.
- Normal e swarm executam ferramentas; um teste com barreira confirma que os três especialistas realmente se sobrepõem em execução.
- Reviewer começa somente após as três contribuições.
- Testados cancelamento, limite de passos, persistência, isolamento de notas por sessão, backup, recuperação de interrupção e exclusão de segunda instância no mesmo banco.
- Testados caminhos fora do workspace, links simbólicos, arquivos grandes, permissões de escrita e argumentos inválidos.
- Adaptadores Ollama e OpenAI-compatible testados com respostas controladas: formato HTTP, normalização de ferramentas, autenticação e falhas.
- Chat direto, chat multiagente, painel da equipe e persistência após recarregar conferidos no navegador.
- Código Python compilado e JavaScript verificado.
- Wheel gerado com Python 3.12.14; seus assets foram conferidos e o pacote extraído serviu API e interface com sucesso.

## Limites da verificação

Não foi feita chamada a um modelo real: nenhum endpoint com modelo ou credencial foi configurado. O comportamento semântico e o desempenho dependem do modelo escolhido, que precisa suportar chamadas de ferramentas. Linux/macOS e Python 3.11 não foram executados nesta máquina.

O ambiente restrito do executor impediu acesso a diretórios temporários criados por Python; a suíte foi executada com acesso normal às pastas temporárias e passou integralmente.

## Reproduzir

```sh
python -W error::ResourceWarning -m unittest discover -s tests -v
python -m compileall -q cairo tests
```

A prévia usada na validação foi encerrada. Para iniciar Cairo, execute `python -m cairo.desktop` na raiz do projeto.


## Atualização 0.2 — aplicativos e microfone

- 42 testes Python passaram, incluindo comandos locais sem modelo, execução única em swarm, recusa de alvos desconhecidos, permissões de desktop e codificação de buscas.
- 5 testes JavaScript passaram para transcrição, limite de texto, falha de permissão, cancelamento e navegador sem suporte.
- A interface foi conferida no navegador integrado: botão de microfone, opção de envio automático e comando composto de aplicativos.
- O comando “Abra o Google Chrome e abra o YouTube Music” foi enviado pela interface e as duas solicitações reais de abertura retornaram sucesso. A conexão de controle do Chrome não estava disponível para inspecionar a página aberta; o retorno confirma despacho, não carregamento do site.
- Nenhum áudio real foi capturado nesta validação. A transcrição depende do microfone e do serviço do navegador; deve ser experimentada pelo usuário após conceder acesso.

Para executar os testes de voz: `node tests/test_voice.cjs`.
