# Cairo 0.4 — revisão e melhorias

## O que foi revisado

Os erros registrados foram agregados sem alterar conversas: aplicativo não encontrado,
limite antigo de seis etapas, resposta vazia do modelo e pasta não reconhecida.
Cancelamentos manuais são ações normais e ficaram fora da contagem de falhas.
Os fluxos de voz, arquivos externos, abertura no VS Code, terminal, navegador e agentes
continuam cobertos pela suíte existente. Esta revisão não garante ausência de todo bug
nem compatibilidade com qualquer aplicativo, site ou modelo.

## Novidades na interface

Em **Ferramentas do dia a dia**, use **Diagnóstico do Cairo** para consultar versão,
processo, etapas, recursos habilitados, dependências e categorias de falhas históricas.
O diagnóstico não confunde uma recusa antiga com um bloqueio atual. Alterações no
código, interface ou metadados do `.env` geram aviso de reinicialização pendente.
A comparação usa a revisão capturada ao iniciar o servidor; não lê tokens do `.env`.
O aviso é verificado ao abrir a página, a cada minuto e ao consultar o diagnóstico.

**Testar conexão da IA** consulta o gateway/provedor configurado. Ollama e APIs
OpenAI-compatible ganharam catálogo e health check, além do FCC já existente. Não
executa inferência nem envia conversas; verifica conectividade, catálogo e nome do
modelo. Um catálogo acessível não garante que uma geração completa será bem-sucedida.
Ollama usa `/api/tags`; OpenAI-compatible usa `/models`. Alguns provedores podem não
oferecer esse endpoint mesmo aceitando chat. URL e autenticação existentes são mantidas.

**Meus atalhos** salva até 12 pedidos neste perfil do navegador. Escreva o pedido,
informe um nome opcional e clique **Salvar pedido atual**. Clicar num atalho apenas
prepara o texto; você decide quando enviar. Os atalhos sobrevivem a recargas, mas não
são sincronizados nem importados para outro navegador. Não salve credenciais neles.

Mensagens ganharam **Copiar**; pedidos do usuário também têm **Reutilizar**, que
preenche o campo sem executar novamente. As permissões de arquivos e o número real de
etapas aparecem na barra lateral.

## Tratamento de erros

- Erros estruturados do provedor mostram sua mensagem em vez de `[object Object]`.
- Requisições da interface têm limite de espera e informam falhas de rede/JSON.
- Erros internos HTTP retornam JSON seguro; logs guardam o tipo da falha, sem corpo,
  prompt, chave ou traceback para o usuário.
- Falhas de recursos locais retornam 503; envio interrompido por tempo retorna 408.
- O adapter HTTP distingue autenticação, rate limit, modelo/endpoint indisponível,
  offline, timeout e resposta inesperada, sem exibir o corpo bruto do provedor.
- Falhas de inicialização do diagnóstico liberam o runtime e seu lock.
- Cancelar uma execução mantém o estado “cancelado”, desliga a escuta contínua e não
  apresenta o cancelamento manual como erro vermelho.

Não há repetição automática de comandos ou operações que alteram o computador.
Se uma solicitação de envio perder a conexão, confira o histórico antes de reenviá-la.
Histórico, configuração do modelo, arquivos pessoais e permissões foram preservados.

## API e testes

`GET /api/diagnostics` devolve diagnóstico local sem credenciais ou prompts.
`GET /api/config` inclui versão e `max_steps`. `GET /api/ai/health` e
`GET /api/ai/models` continuam sendo as entradas de diagnóstico do provedor.

```powershell
python -m unittest discover -s tests -v
$env:CAIRO_TEST_BROWSER='1'
$env:CAIRO_TEST_DESKTOP='1'
python -m unittest discover -s tests -v
node tests/test_voice.cjs
node tests/test_client.cjs
```

Os testes opcionais usam Chrome e uma janela de teste própria. Não editam seus
documentos. Os testes de interface verificam diagnóstico, atalhos persistentes e
aviso de atualização. A geração ao vivo no FCC continua sendo um teste separado,
opt-in, usando o modelo configurado.
