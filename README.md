# Aizen Auto Editor

Editor local para transformar gameplays longas de Free Fire em uma sugestão de vídeo para YouTube. Ele não usa Codex nem APIs pagas durante a edição comum.

## Estado do MVP

O fluxo já está implementado: carregar vídeo → FFprobe → transcrição local opcional → análise leve de áudio/movimento → candidatos de combate v1 → highlights revisáveis → EDL → preview/final FFmpeg → validação de FPS, áudio e duração. Análise e renderização mostram etapa/porcentagem e podem ser canceladas.

O detector de combate é heurístico (movimento + energia de áudio + HUD) e adapta o limite à faixa superior de atividade de cada gravação. Picos de combate recebem prioridade adicional. O placar azul/laranja de fim de round também é reconhecido pela sua geometria e preserva pelo menos cinco segundos anteriores, onde normalmente acontece a kill ou morte. A transcrição gera candidatos determinísticos de conversa, reação, provocação, chamadas curtas de Free Fire, kill, morte e pausa. Falas genéricas têm contribuição baixa e limitada para não superarem a ação apenas pelo acúmulo de frases.

As partes mortas são detectadas somente quando a baixa atividade é sustentada e coincide em vários sinais: pouco movimento, áudio baixo, ausência de fala e ausência de mudança relevante no HUD. Essas zonas separam highlights próximos e aparam o excesso de contexto; silêncio isolado durante combate não é cortado. Cadeias longas de eventos são divididas em clipes menores e os contextos vizinhos não repetem os mesmos frames.

## Instalação no Windows

1. Confirme que `ffmpeg` e `ffprobe` estão no PATH (já detectados neste computador).
2. Execute `setup.bat`.
3. `setup.bat` instala o backend local `faster-whisper`.

Na primeira transcrição, o modelo local é baixado uma única vez. Este computador usa CPU + `int8`: a Radeon RX 6800 XT não é aproveitada por `faster-whisper` no Windows, pois o backend GPU dele exige CUDA/NVIDIA. A análise visual continua caso o backend não esteja disponível.

Para renderização, o aplicativo usa `h264_amf` da Radeon RX 6800 XT quando `use_hardware_encoder` está ativo em `config/default.json`, inclusive na etapa final que aplica legendas. Caso AMF não esteja disponível no driver, cada segmento volta automaticamente para `libx264` em CPU.

Para controlar a temperatura, o padrão limita o FFmpeg a `cpu_threads: 4` e `filter_threads: 2` no mesmo arquivo. Em um Ryzen 9 5900X de 24 threads lógicas, isso reduz bastante a carga de CPU durante a edição; aumente ou diminua esses números apenas se necessário.

### LLM local opcional

`config/default.json` deixa o LLM local desativado. Quando desejar testar um Ollama local, defina `enabled` como `true` e informe um `model`. Essa integração é somente para trechos pequenos de transcrição e não é necessária para editar vídeos.

## Validação realizada

Foi validado o pipeline completo com `C:\Users\Aizen\Videos\2026-08-07 11-23-25.mp4` (4,42 s, HEVC 1920×1080, 60 FPS, AAC): FFprobe, transcrição local `faster-whisper`, análise, highlight, EDL, preview com legenda e final. O preview preservou 60 FPS em 1280×720 e o final preservou 60 FPS em 1920×1080; ambos mantiveram áudio AAC.

## Primeiro uso

1. Execute `start.bat`.
2. Acesse `http://127.0.0.1:8000` se o navegador não abrir automaticamente.
3. Para continuar um trabalho após fechar o app, escolha-o em **Projetos recentes**; highlights, EDL e análises persistidas são reabertos sem reprocessar o vídeo.
3. Clique em **Selecionar arquivo** ou cole o caminho completo da gameplay e clique em **Carregar vídeo**.
4. Escolha a duração automática, aproximada ou personalizada.
5. Clique em **Analisar vídeo**, revise os momentos e desmarque os indesejados.
6. Clique em **Gerar edição (EDL)**, depois **Gerar preview** ou **Renderizar final**.

### Editor básico

Após montar a edição, a área **Ajustar edição** permite corrigir o início e fim dos cortes, remover, adicionar ou reordenar trechos, além de editar texto e tempo das legendas. Clique em **Salvar alterações** antes de gerar o preview ou o vídeo final. Essas mudanças ficam somente no projeto; o vídeo original nunca é alterado.

## Aplicativo Windows

Para abrir em uma janela nativa, sem terminal e sem precisar abrir o navegador, use **`Aizen Auto Editor.bat`**. Para gerar um executável distribuível, execute `build-windows.bat`; o resultado fica em `dist\Aizen Auto Editor\Aizen Auto Editor.exe`.

Quando há uma duração definida, o editor prioriza os highlights de maior score até o limite aproximado e sempre os organiza na ordem cronológica da gameplay.

No modo de duração **Automática**, vídeos com até dois minutos recebem uma edição proporcionalmente curta (em vez de contexto excessivo). O limite e o contexto para esses vídeos ficam configuráveis em `config/freefire.json`.

O tipo de edição influencia a sugestão: **Mais dinâmica** encurta o contexto e agrupamento; **Mais natural** preserva mais preparação e consequência; **Só melhores momentos** eleva o limiar de seleção. A edição automática usa os valores padrão do Free Fire em `config/freefire.json`.

Ao salvar a EDL, o app valida os limites ajustados manualmente e registra decisões de manter, remover ou favoritar em `feedback.jsonl` para aprendizagem futura.

O vídeo original nunca é modificado. Cada projeto vai para `projects/<vídeo>-<id>/`; ali ficam `source.json`, transcrições, análise, highlights, `edl.json`, `preview.mp4`, `final.mp4`, validações e feedback.

`log.txt` registra etapas importantes do projeto, como transcrição, análise, EDL e renderização, sem inundar o terminal.

Quando legendas estiverem ativadas, `subtitles.srt` é gerado localmente com timestamps remapeados para a edição final. Toda fala que atravessa um trecho escolhido é legendada, inclusive no modo **Apenas momentos importantes**, pois o próprio trecho já passou pela seleção editorial. As frases são divididas usando os tempos de cada palavra em blocos de até cinco palavras, 32 caracteres, duas linhas e aproximadamente 2,4 segundos, facilitando a leitura durante a ação.

Se não houver fala dentro de um trecho selecionado, a renderização segue normalmente sem criar um arquivo de legenda vazio.

Ao renderizar, o app usa a calibração para escolher automaticamente uma faixa de legenda entre topo, meio e base, evitando webcam e HUD quando eles forem marcados. A revisão também mostra uma timeline clicável de atividade, eventos e highlights. Frames dos candidatos visuais ficam em `debug/` com o rótulo de detector **candidato** para facilitar ajustes futuros.

Na revisão de highlights, o seletor **Efeito** permite aplicar manualmente Punch Zoom, Webcam Punch-In, Freeze Frame, câmera lenta ou texto. Zoom, webcam e texto ocupam uma janela curta no começo do highlight; freeze e câmera lenta atuam no highlight escolhido. Eles são associados ao momento revisado; o sistema não os aplica aleatoriamente. Webcam Punch-In exige a região da webcam calibrada.

A intensidade selecionada também é aplicada de fato: **Baixo**, **Médio** e **Alto** mudam a força do zoom, o tempo de freeze, a velocidade da câmera lenta e o tamanho do texto. **Nenhum** bloqueia a associação de novos efeitos.

As chaves em `config/freefire.json` também são respeitadas ao salvar a EDL: se um tipo estiver desativado, o backend recusa essa associação de efeito de forma explícita.

Para usar um som próprio, coloque um arquivo WAV, MP3, AAC, M4A, OGG ou FLAC em `assets/sfx/`, atualize a página e selecione-o no highlight. O som é misturado localmente no início desse trecho; nenhum arquivo é baixado nem escolhido automaticamente.

O detector de possível abate/morte combina três fontes: placar de fim de round, chamadas faladas como “matei” ou “morri” e, quando calibradas, mudanças nas regiões de kill feed ou HP. Sem calibração, o app ainda prioriza os fins de round e os picos de combate, mas mantém os demais sinais visuais como candidatos para não afirmar uma kill incorreta.

## Calibração de layout

A página **Configurar layout do Free Fire** extrai um frame, permite escolher webcam, placar, kill feed, HP, minimapa ou centro de gameplay e desenhar o retângulo diretamente sobre a imagem. Os campos `x`, `y`, `w` e `h` continuam visíveis para ajustes finos; nenhuma posição é fixada no código.

## Estrutura

- `app/core`: análise, EDL, renderização e verificações.
- `app/web`: interface local.
- `config/freefire.json`: pesos de ranking e recursos de efeitos.
- `config/default.json`: limiares e qualidade do preview.
- `tests`: regras críticas, incluindo FPS e EDL.

## Solução de problemas

- **Página não inicia:** rode `setup.bat` uma vez e execute novamente `start.bat`.
- **FFmpeg não encontrado:** instale uma build Windows e adicione a pasta `bin` ao PATH.
- **Sem transcrição:** execute `setup.bat` para instalar `faster-whisper`. O aplicativo usa CPU com `int8` como fallback local; se a transcrição ainda falhar, o restante do pipeline continua disponível e mostra o motivo na tela.
- **Render falha com AMF:** o app tenta `h264_amf` na Radeon e volta automaticamente para `libx264` com limite de threads se o driver recusar o encoder.

## Desenvolvimento

Execute `python -m pytest`. Consulte `ARCHITECTURE.md` e `AGENTS.md` antes de ampliar módulos.
