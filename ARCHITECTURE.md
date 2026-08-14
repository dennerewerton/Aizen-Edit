# Arquitetura — Aizen Auto Editor

## Decisões

O MVP é uma aplicação local FastAPI com HTML/CSS/JavaScript nativos. O núcleo Python é independente da web, portanto pode ganhar depois uma interface desktop ou CLI sem alterar a análise e a renderização. Não há APIs externas na edição normal.

O pipeline é incremental e persistente:

```text
origem (somente leitura) → ffprobe → áudio/transcrição local → análise leve
→ eventos → ranking/agrupamento → highlights revisáveis → EDL → FFmpeg → verificação
```

Cada arquivo recebe um projeto em `projects/<nome>-<hash>/`. Artefatos JSON permitem retomar o trabalho sem refazer análise. Um identificador (tamanho + data de modificação + hash parcial) invalida o cache quando a origem muda.

Análise e renderização são jobs locais em background. A interface consulta o estado e pode cancelar; resultados de cada etapa já concluída permanecem no projeto e são reutilizados na abertura seguinte.

## Módulos

- `probe`: metadados via FFprobe, incluindo FPS racional.
- `audio`: energia por janela com FFmpeg; sem carregar áudio inteiro.
- `transcription`: interface de backends; `faster-whisper` local é opcional e há backend indisponível explícito até o modelo ser instalado.
- `speech`: sinais editoriais determinísticos extraídos dos timestamps da transcrição; um LLM local futuro pode complementar, mas não substitui o pipeline.
- `gameplay`: amostragem OpenCV, diferença de luminância/movimento e eventos candidatos. Detectores de kill/death são v1 heurísticos, não alegações de detecção perfeita.
- `highlights` e `ranking`: agrupam eventos e produzem candidatos configuráveis.
- `edl`: decisões editáveis e duração derivada.
- `renderer`: extração por segmento com fades, concatenação, preview/final e preservação de FPS.
- `verify`: FFprobe do resultado e checagens de integridade.
- `jobs`: estado/cancelamento para operações longas, sem serviço externo.
- `layout` e `thumbnails`: calibração normalizada do HUD e revisão visual de highlights.

## Hardware e dependências

Ambiente identificado: Windows 11 64-bit, Ryzen 9 5900X, AMD Radeon RX 6800 XT, Python 3.14 e FFmpeg 2023. A build FFmpeg lista `h264_amf` e `hevc_amf`; o render tenta AMF se configurado e cai para `libx264` se falhar. OpenCV já está disponível. FastAPI e Uvicorn são instalados pelo `setup.bat`. `faster-whisper` é opcional porque ainda pode não oferecer rodas para Python 3.14; o aplicativo avisa claramente e a análise visual continua funcional.

## Referência externa

`browser-use/video-use` foi inspecionado (README, install, SKILL e helpers). Ele está sob MIT. Não copiamos seu código. Adotamos apenas princípios compatíveis: cache por origem, EDL persistente, fades de áudio curtos, visualização sob demanda e validação final por FFprobe.

## Limites do MVP

OCR de kill feed, reconhecimento facial, legendas queimadas e efeitos temporizados são pontos de extensão, não detectores completos nesta primeira versão. A interface já persiste layout normalizado e decisões do usuário para treinamento futuro.
