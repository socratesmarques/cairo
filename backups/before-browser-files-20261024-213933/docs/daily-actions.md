# Cairo: ações do dia a dia

Esta atualização acrescenta pastas pessoais do Windows, clima e previsão, leitura de páginas públicas, controles de mídia e volume, hora local e diagnóstico das capacidades habilitadas. Comandos diretos executam uma única vez nos modos normal e swarm, mesmo se o modelo estiver offline. Pedidos mais complexos continuam sendo interpretados pelo modelo e usam o mesmo catálogo de ferramentas.

## Exemplos por texto ou microfone

| Pedido | Comportamento |
| --- | --- |
| Cairo, abra a pasta download | Abre a pasta Downloads registrada pelo Windows no Explorador |
| Abra Documentos e abra Imagens | Solicita as duas aberturas, uma vez cada |
| Abra a Área de Trabalho | Abre a pasta real, inclusive se redirecionada ao OneDrive |
| Como está o clima agora? | Consulta a cidade padrão configurada |
| Como está o clima em Recife, Pernambuco? | Consulta a cidade informada; pede esclarecimento se houver homônimos |
| Previsão do tempo amanhã | Mostra condições atuais e previsão para hoje/amanhã na cidade padrão |
| Liste os arquivos da pasta downloads | Lista até 200 entradas, com acesso pessoal habilitado |
| Leia o arquivo notas.txt de Downloads | O modelo pode usar read_personal_file para ler texto UTF-8, até 64 KiB |
| Leia https://example.com | Busca o texto da página HTTPS e informa a fonte |
| Resuma https://example.com | O modelo usa a ferramenta de leitura e produz o resumo |
| Abra https://example.com | Abre uma página pública HTTPS no navegador |
| Aumente o volume / Abaixe o volume | Envia um comando de volume ao Windows |
| Próxima música / Música anterior / Pare a música | Envia o controle ao aplicativo de mídia ativo |
| Reproduza ou pause a música | Alterna reprodução/pausa; não seleciona uma faixa |
| Alterne o mudo | Alterna o estado mudo do sistema |
| Que horas são? | Informa data e hora local e UTC offset |
| O que você pode fazer? | Lista funções e limites, respeitando as permissões atuais |

Os aliases de pastas também incluem Downloads, Documentos, Desktop, Imagens/Fotos, Músicas e Vídeos. A ferramenta de abertura aceita subpastas relativas; listar e ler pastas pessoais não permite executar arquivos ou escrever fora do workspace.

## Configuração

No `.env`, reiniciando Cairo depois de alterar:

```dotenv
CAIRO_ALLOW_DESKTOP=true
CAIRO_WEATHER_CITY=Maranguape, Ceará
CAIRO_ALLOW_PERSONAL_FILES=true
CAIRO_ALLOW_NETWORK=true
```

O exemplo distribuído mantém leitura pessoal desativada por padrão. A instalação do usuário habilita essa leitura para atender ao pedido de ações pessoais. `CAIRO_ALLOW_WRITE` continua controlando exclusivamente escrita no workspace. As novas variáveis também aparecem em `GET /api/config`, sem credenciais.

## Clima

Dados de modelos meteorológicos de [Open-Meteo](https://open-meteo.com/en/docs), com localização pela [API de geocoding](https://open-meteo.com/en/docs/geocoding-api). Uso pessoal não comercial sem chave, sujeito às condições e limites do serviço. A saída inclui fonte, horário informado pelo serviço e fuso da cidade, temperatura, sensação, umidade, vento, mínimas/máximas e probabilidade de chuva para hoje e amanhã. Não é uma medição de uma estação na casa do usuário.

Cada consulta busca dados novos; falhas de rede, cidade ausente e respostas inválidas são apresentadas explicitamente. Cairo não infere localização por IP/GPS. Se o nome tiver mais de uma correspondência, mostra opções e pede cidade/estado/país. Não usa o modelo para inventar condições atuais.

## Fronteiras de acesso

Pastas pessoais são resolvidas por `SHGetKnownFolderPath`, respeitando redirecionamentos do Windows. Caminhos relativos não podem escapar da pasta, atravessar links/junções, usar streams NTFS ou apontar para outra unidade. A leitura pessoal é somente texto UTF-8 e não transforma PDFs, Word, planilhas ou imagens em texto.

A leitura web aceita HTTPS público, limita 1 MB de resposta e 12 mil caracteres extraídos, rejeita credenciais/portas alternativas/endereços privados e verifica cada redirecionamento. Resolve DNS e fixa o IP validado na conexão TLS, mantendo a validação do hostname. Não usa cookies, login, JavaScript nem baixa executáveis. Texto de páginas é evidência não confiável; não concede permissões nem autoriza ações. `open_url` valida o destino inicial; a navegação posterior no navegador segue as regras do próprio navegador.

Controles de mídia são pares de eventos de tecla limitados a sete ações conhecidas, via `SendInput`. A ferramenta não aceita teclas arbitrárias nem executa shell. Retorno de sucesso significa que Windows aceitou o comando, não prova visual de que o player mudou. Reprodução/pausa e mudo são alternâncias. Aplicativos elevados e players que não suportam mídia do Windows podem ignorar comandos.

## Inicialização

```powershell
python -m cairo.desktop
```

Se a mesma instância já responde na porta configurada e usa a mesma pasta de dados, o lançador abre sua interface sem iniciar outro runtime. O bloqueio de dados permanece ativo para evitar corrupção. Se outra instância usa a pasta em outra porta, o erro de bloqueio continua válido. Não apague `storage/runtime.lock` para contorná-lo.

## Limites ainda existentes

Esta entrega não equivale a controle universal do computador. Cliques visuais gerais, automação de formulários autenticados, seleção/reprodução de uma faixa específica no YouTube Music, busca com leitura automática dos resultados do Google, terminal arbitrário, instalação de programas, integração com iPhone, palavra de ativação e reconhecimento offline ainda precisam de integrações próprias. Voz permanece no navegador, com a página aberta, pausando durante execução/fala e sem fila de comandos. Lembretes aparecem com a interface aberta; não há serviço de notificações independente do navegador.

## Validação

```powershell
python -m unittest discover -s tests -v
python -m compileall -q cairo tests
node --test tests/test_voice.cjs
```

Os testes novos verificam interpretação ancorada, permissões, leitura e escape de caminhos, chamadas únicas sem modelo, parsing meteorológico, falhas de rede, destinos web privados/redirecionamentos, extração HTML, eventos de mídia e reutilização da instância. Eventos de mídia são simulados para não alterar o som durante testes. A consulta real de clima, localização de Downloads e leitura HTTPS pública também são verificadas na instalação; o teste automatizado não depende da internet.
