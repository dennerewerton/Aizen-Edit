# Aizen Auto Editor

Editor local para transformar gameplays longas de Free Fire em uma sugestão de vídeo para YouTube. Ele não usa Codex nem APIs pagas durante a edição comum.

## Estado do MVP

O fluxo já está implementado: carregar vídeo → FFprobe → transcrição local opcional → análise leve de áudio/movimento → candidatos de combate v1 → highlights revisáveis → EDL → preview/final FFmpeg → validação de FPS e áudio. Análise e renderização mostram etapa/porcentagem e podem ser canceladas.

O detector de combate é heurístico v1 (movimento + energia de áudio). A transcrição também gera candidatos determinísticos de conversa, reação, provocação e pausa. Kill feed/OCR, mortes, reações faciais, legendas e efeitos temporizados são extensões planejadas, não promessas concluídas.

## Instalação no Windows

1. Confirme que `ffmpeg` e `ffprobe` estão no PATH (já detectados neste computador).
2. Execute `setup.bat`.
3. Opcionalmente, instale transcrição local: `python -m pip install faster-whisper`.

O `faster-whisper` baixa um modelo local no primeiro uso. Sem ele, a análise visual continua e a interface informa que a transcrição não está disponível.

## Primeiro uso

1. Execute `start.bat`.
2. Acesse `http://127.0.0.1:8000` se o navegador não abrir automaticamente.
3. Cole o caminho completo da gameplay e clique em **Carregar vídeo**.
4. Clique em **Analisar vídeo**, revise os momentos e desmarque os indesejados.
5. Clique em **Gerar edição (EDL)**, depois **Gerar preview** ou **Renderizar final**.

O vídeo original nunca é modificado. Cada projeto vai para `projects/<vídeo>-<id>/`; ali ficam `source.json`, transcrições, análise, highlights, `edl.json`, `preview.mp4`, `final.mp4`, validações e feedback.

## Calibração de layout

A página **Configurar layout do Free Fire** salva webcam, placar, kill feed, HP, minimapa e centro de gameplay como regiões normalizadas. Preencha `x`, `y`, `w` e `h` de 0 a 1; nenhuma posição é fixada no código.

## Estrutura

- `app/core`: análise, EDL, renderização e verificações.
- `app/web`: interface local.
- `config/freefire.json`: pesos de ranking e recursos de efeitos.
- `config/default.json`: limiares e qualidade do preview.
- `tests`: regras críticas, incluindo FPS e EDL.

## Solução de problemas

- **Página não inicia:** rode `setup.bat` uma vez e execute novamente `start.bat`.
- **FFmpeg não encontrado:** instale uma build Windows e adicione a pasta `bin` ao PATH.
- **Sem transcrição:** instale `faster-whisper`; em Python 3.14 ele pode ainda não possuir uma distribuição compatível. O restante do MVP funciona sem ele.
- **Render falha com AMF:** o atual render usa `libx264` de forma estável. A aceleração AMD está documentada para evolução futura, depois de um vídeo real de teste.

## Desenvolvimento

Execute `python -m pytest`. Consulte `ARCHITECTURE.md` e `AGENTS.md` antes de ampliar módulos.
