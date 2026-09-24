# Variaveis

| Variavel | Padrao | Uso |
| --- | --- | --- |
| APP_ENV | local | Ambiente informado no health |
| MAX_UPLOAD_MB | 100 | Total de arquivos por operacao |
| MAX_PAGES | 500 | Limite de paginas de entrada e resultado |
| MAX_CONCURRENT_JOBS | 1 no Compose, 2 em Python | Trabalhos simultaneos por processo |
| TOOL_TIMEOUT_SECONDS | 300 | Timeout OCR/Office/Word |
| ALLOWED_ORIGINS | GitHub Pages e localhost | Origens completas separadas por virgula |
| WORK_DIR | work local, /tmp/modupdf no Docker | Raiz dos diretorios temporarios |
| TEMP_TTL_SECONDS | 3600 | Idade minima de residuos para limpeza |

Mantenha um worker Uvicorn: o limite de concorrencia e por processo. Ajuste
memoria, tmpfs e limite Nginx junto dos limites da API. Nunca publique `.env`,
certificados privados ou access keys. Certificado TLS fica em `deploy/certs/`.
