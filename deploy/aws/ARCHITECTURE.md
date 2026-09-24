# Arquitetura atual

```text
Frontend ModuPDF (Nginx ou GitHub Pages)
  -> HTTPS :443
  -> Nginx (EC2 exclusiva modupdf)
  -> FastAPI :8000 (somente rede Docker)
  -> Bibliotecas Python / subprocessos OCR e LibreOffice
  -> Diretorio isolado por requisicao em tmpfs
  -> Download -> limpeza automatica
```

Docker limita memoria, processos e concorrencia. Nginx limita corpo multipart,
desabilita buffering em disco e aplica timeout. CORS permite somente as origens
configuradas. Logs nao incluem conteudo de arquivos.

Escala futura: API -> fila -> workers dedicados -> objetos temporarios S3 com
expiracao. Planos, autenticacao e cobranca entram apos homologar o processamento.
Todos os recursos pertencem ao ModuPDF e ficam separados do GeoVida.
