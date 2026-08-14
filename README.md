# Aizen Auto Editor

Editor local para transformar gameplays longas de Free Fire em uma sugestão de vídeo para YouTube. Ele não usa Codex nem APIs pagas durante a edição comum.

## Estado do MVP

O fluxo já está implementado: carregar vídeo → FFprobe → transcrição local opcional → análise leve de áudio/movimento → candidatos de combate v1 → highlights revisáveis → EDL → preview/final FFmpeg → validação de FPS e áudio. Análise e renderização mostram etapa/porcentagem e podem ser canceladas.

O detector de combate é heurístico v1 (movimento + energia de áudio). A transcrição também gera candidatos determinísticos de conversa, reação, provocação e pausa. Kill feed/OCR, mortes, reações faciais, legendas e efeitos temporizados são extensões planejadas, não promessas concluídas.

## Instalação no Windows

1. Confirme que `ffmpeg` e `ffprobe` estão no PATH (já detectados neste computador).
2. Execute `setup.bat`.
3. `setup.bat` instala o backend local `faster-whisper`.

Na primeira transcrição, o modelo local é baixado uma única vez. Este computador usa CPU + `int8`: a Radeon RX 6800 XT não é aproveitada por `faster-whisper` no Windows, pois o backend GPU dele exige CUDA/NVIDIA. A análise visual continua caso o backend não esteja disponível.

Para renderização, o aplicativo tenta `h264_amf` da Radeon RX 6800 XT quando `use_hardware_encoder` está ativo em `config/default.json`. Caso AMF não esteja disponível no driver, cada segmento volta automaticamente para `libx264` em CPU.

### LLM local opcional

`config/default.json` deixa o LLM local desativado. Quando desejar testar um Ollama local, defina `enabled` como `true` e informe um `model`. Essa integração é somente para trechos pequenos de transcrição e não é necessária para editar vídeos.

## Validação realizada

Foi validado o pipeline completo com `C:\Users\Aizen\Videos\2026-08-07 11-23-25.mp4` (4,42 s, HEVC 1920×1080, 60 FPS, AAC): FFprobe, transcrição local `faster-whisper`, análise, highlight, EDL, preview com legenda e final. O preview preservou 60 FPS em 1280×720 e o final preservou 60 FPS em 1920×1080; ambos mantiveram áudio AAC.

## Primeiro uso

1. Execute `start.bat`.
2. Acesse `http://127.0.0.1:8000` se o navegador não abrir automaticamente.
3. Clique em **Selecionar arquivo** ou cole o caminho completo da gameplay e clique em **Carregar vídeo**.
4. Escolha a duração automática, aproximada ou personalizada.
5. Clique em **Analisar vídeo**, revise os momentos e desmarque os indesejados.
6. Clique em **Gerar edição (EDL)**, depois **Gerar preview** ou **Renderizar final**.

Quando há uma duração definida, o editor prioriza os highlights de maior score até o limite aproximado e sempre os organiza na ordem cronológica da gameplay.

Ao salvar a EDL, o app valida os limites ajustados manualmente e registra decisões de manter, remover ou favoritar em `feedback.jsonl` para aprendizagem futura.

O vídeo original nunca é modificado. Cada projeto vai para `projects/<vídeo>-<id>/`; ali ficam `source.json`, transcrições, análise, highlights, `edl.json`, `preview.mp4`, `final.mp4`, validações e feedback.

`log.txt` registra etapas importantes do projeto, como transcrição, análise, EDL e renderização, sem inundar o terminal.

Quando legendas estiverem ativadas, `subtitles.srt` é gerado localmente com timestamps remapeados para a edição final. No modo **Apenas momentos importantes**, o MVP mantém falas enfáticas, reações e provocações detectadas; **Todas as falas** mantém toda fala que atravessa um segmento escolhido.

Ao renderizar, o app usa a calibração para escolher automaticamente uma faixa de legenda entre topo, meio e base, evitando webcam e HUD quando eles forem marcados. A revisão também mostra uma timeline clicável de atividade, eventos e highlights. Frames dos candidatos visuais ficam em `debug/` com o rótulo de detector **candidato** para facilitar ajustes futuros.

Na revisão de highlights, o seletor **Efeito** permite aplicar manualmente Punch Zoom, Webcam Punch-In, Freeze Frame, câmera lenta ou texto. Zoom, webcam e texto ocupam uma janela curta no começo do highlight; freeze e câmera lenta atuam no highlight escolhido. Eles são associados ao momento revisado; o sistema não os aplica aleatoriamente. Webcam Punch-In exige a região da webcam calibrada.

O detector de possível abate/morte é conservador: ele depende de atividade de combate e de mudanças em regiões de kill feed ou HP que você calibrar. Sem essa calibração, o app mostrará combates e conversas, mas não inventará um abate.

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
- **Render falha com AMF:** o atual render usa `libx264` de forma estável. A aceleração AMD está documentada para evolução futura, depois de um vídeo real de teste.

## Desenvolvimento

Execute `python -m pytest`. Consulte `ARCHITECTURE.md` e `AGENTS.md` antes de ampliar módulos.
