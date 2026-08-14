# Aizen Auto Editor

## Arquitetura

- `app/core` contém regras de domínio e nunca depende da camada web.
- `app/web` contém somente interface e endpoints.
- `renderer` é o único módulo que chama FFmpeg para gerar mídia.
- Vídeos de origem são estritamente somente leitura; todos os resultados ficam em `projects/`.

## Comandos

- Instalar: `setup.bat`
- Iniciar: `start.bat` ou `python -m app`
- Testar: `python -m pytest`

## Regras obrigatórias

- Use `pathlib`, caminhos relativos ao projeto e JSON UTF-8.
- Preserve FPS, resolução e proporção por padrão.
- Não carregue o vídeo inteiro ou todos os frames na memória.
- Toda operação cara precisa persistir e poder reutilizar o cache.
- Antes de concluir uma feature: teste unitário, teste de integração aplicável, FFprobe do resultado e atualização da documentação.

