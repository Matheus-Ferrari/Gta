# Vice Clips

Editor local de cortes de lives. Encontra os melhores momentos, monta o layout vertical e exporta o Reel em 1080x1920. Tudo roda no seu PC, sem serviços pagos.

## Instalar em outro PC

1. Baixe o projeto: botão **Code → Download ZIP** no GitHub (ou `git clone`) e extraia numa pasta.
2. Tenha o Python 3.11 ou mais novo (`winget install Python.Python.3.13`).
3. Dê dois cliques em `instalar.cmd`. Ele cria o ambiente, instala os pacotes e baixa o ffmpeg 8.0.1 e o TwitchDownloader. Demora na primeira vez.
4. Abra com `abrir_painel.cmd`. Em **Configurações → Twitch**, informe um Client ID (crie grátis em dev.twitch.tv/console, tipo *Public*) e conecte a sua conta.

Vídeos e configurações ficam em `D:\Cortes` quando existe o disco D:, senão em `ViceClips` na pasta do usuário (a variável `CORTES_DADOS` escolhe outra). Placa NVIDIA deixa a legenda e a exportação bem mais rápidas, mas não é obrigatória.

O app roda só no PC de quem instalou: não é um site (o GitHub Pages não executa Python, ffmpeg nem a placa de vídeo).

## Abrir

Dê dois cliques em `abrir_painel.cmd`. O painel abre em `http://127.0.0.1:8765` e só funciona neste PC. Feche a janela preta para desligar.

| Tela | Para que serve |
| --- | --- |
| Início | Resumo, quem está ao vivo, cortes recentes (com exclusão em massa) e fila de tarefas |
| Lives | Ao vivo agora, Clipes em alta (por idioma, criador e quem clipou), Favoritos, Monitoramento, Meus canais e Clips criados |
| Gerar Cortes | Manual: abre gravação ou arquivo, marca início e fim. Automático: sugere cortes com nota |
| Meus Cortes | Reels exportados e cortes por estado: só link, pronto para editar, em edição, exportado |
| Editor | Layout, webcam, títulos, legendas, timeline e exportação |
| Referências | Links de vídeos de referência, análise de arquivos seus e a biblioteca de boas práticas (com fonte e data) |
| Configurações | Credenciais da Twitch e da Kick |

## Fluxo

Gravação ou arquivo → marcar o momento → template → editar → prévia → exportar.

1. **Gerar Cortes → Escolher o momento** (ou Lives → Gravações / VODs). Cole o link da gravação da Twitch ou da Kick, ou clique em **Arquivo do PC** (MP4, MOV, MKV).
2. Twitch abre no player oficial. Kick não tem player oficial para gravações: digite os horários, o editor dá 30 s de folga para o ajuste fino.
3. Marque início e fim (teclas I e O), confirme a autorização e clique em **Criar corte**. Só o trecho, com folga, é processado. Na Twitch o chat do trecho também vem junto.
4. Escolha o template. O padrão é o **Vice Cortes Clássico**: webcam em cima, faixa branca com título, gameplay embaixo.

## Editor

- **Fonte original**: arraste os retângulos (rosa = webcam, azul = gameplay, laranja = chat do vídeo). **Salvar regiões do streamer** faz os próximos vídeos dele abrirem iguais.
- **Templates**: 9 composições, todas editáveis. Nos empilhados, o controle *Espaço da webcam* define quem ganha mais espaço.
- **Camadas**: a mesma fonte pode entrar várias vezes (**Duplicar** ou **+ Recorte**), cada uma com seu recorte (retângulo amarelo). Também há título, chat (só mensagens reais) e imagem do PC.
- **Título**: quebra automática, faixas branca, vermelha, preta ou transparente, altura e linha da faixa.
- **Legendas**: texto, sincronia, `*palavra*` em destaque, estilos e posição livre.
- **Timeline**: início, fim, duração e volume.
- **Exportar**: qualidade Alta, Média ou Leve com tamanho estimado. Depois, **Comparar** mostra o original e o MP4 lado a lado.

Arquivos do PC são renderizados direto do original. Gravações baixam o trecho uma vez, em alta qualidade, e cada exportação recodifica só a duração do corte.

Atalhos: espaço reproduz ou pausa, Ctrl+Z desfaz.

## Novidades do editor (2.0)

- **Formato**: 9:16, 16:9 ou 1:1, escolhido ao criar o corte e trocável no topo do editor.
- **Aba Templates**: todos os layouts sempre à mão, e **Meus templates** para salvar a composição atual.
- **Timeline**: alça para aumentar ou diminuir, botão Recolher. **+ Trecho** e **Dividir** criam vários trechos da mesma gravação, com velocidade (câmera lenta) e transição (corte, fade, flash).
- **Efeitos**: zoom na webcam, webcam ampliada (centralizada no rosto, ocupa 70% da tela por padrão), zoom progressivo, tremor, freeze, flash, preto e branco (entrada e saída graduais), vinheta. Preset **Choque**: corte para a reação, cor sumindo, impacto, trilha de suspense e volta ao normal.
- **Áudio**: volume por trilha, pontos de volume, fades, música que abaixa nas falas (pela transcrição), sons originais por categoria, importação de áudio seu e presets (suspense, pânico, impacto, comédia, falha, revelação, reação). Um limitador evita áudio estourado.
- **Área segura**: mostra na prévia a parte coberta pela interface dos apps.
- **Delete** apaga a camada ou o bloco selecionado; Ctrl+Z desfaz.

## Nota dos cortes

A nota estima a relevância do momento e não prevê alcance. Ela combina a voz acima do normal, reações súbitas, risadas e gritos, o crescimento e as repetições do chat e as palavras de reação. Falas sobre agenda, horários e avisos perdem pontos. Cada corte mostra o motivo da nota.

Eventos visuais do jogo não entram no cálculo.

## Twitch e Kick

| Função | Situação |
| --- | --- |
| Status ao vivo na Twitch | Exige Client ID gratuito e conta conectada |
| Criar clip na Twitch | Exige conta conectada, canal ao vivo e clips liberados pelo canal |
| Baixar clip da Twitch | A Twitch libera só ao dono do canal e aos editores dele |
| Sugestões pelo chat da Twitch | Avisa quando o chat acelera. Quem decide criar o clip é você |
| Status ao vivo na Kick | Exige Client ID e Client Secret gratuitos |
| Clips na Kick | A Kick não oferece API. Use o link da gravação em Gravações / VODs |
| Gravação da Twitch | Dados pela API oficial e player oficial. O trecho só é baixado com autorização confirmada |
| Clip sem permissão de download | Fica como "Só link". Use Importar arquivo autorizado se o criador enviar o arquivo |
| Captura contínua da live | Não disponível. Use o link da gravação quando a live terminar |

## Pelo terminal

```bash
cortar.cmd "https://www.twitch.tv/videos/123456789" --qtd 5 --dur-min 15 --dur-max 60
```

| Opção | Para que serve |
| --- | --- |
| `--qtd 5` | Quantos cortes gerar |
| `--dur-min 15` e `--dur-max 60` | Duração mínima e máxima de cada corte, em segundos |
| `--inicio 01:00:00` | Começa a analisar a partir desse horário |
| `--minutos 30` | Analisa só essa quantidade de minutos |
| `--webcam x,y,largura,altura` | Webcam em frações da tela, de 0 a 1 |
| `--chat arquivo` | Chat em JSON do TwitchDownloader ou CSV `segundos,mensagem` |
| `--modelo medium` | Whisper: `small`, `medium` ou `large-v3` |
| `--so-analisar` | Lista os cortes sem gerar os vídeos |

## Instalação no PC atual

- Python e pacotes: `D:\Cortes\.venv` neste PC, ou `.venv` na pasta do projeto quando instalado pelo `instalar.cmd` (lista em `requirements.txt`).
- Modelos do Whisper: `D:\Cortes\modelos`.
- ffmpeg: `D:\Cortes\tools\ffmpeg`, na versão **8.0.1**. Não atualize: o ffmpeg 9 exige driver NVIDIA 610 ou mais novo, e sem ele os vídeos passam a ser gerados pela CPU.
- OpenCV: mantenha a versão 4. A versão 5 não traz o detector de rostos usado para achar a webcam.
- TwitchDownloader CLI 1.56.5: `D:\Cortes\tools\TwitchDownloader`.
- Credenciais e preferências: `D:\Cortes\config.json`, `streamers.json` e `estilos.json`.
