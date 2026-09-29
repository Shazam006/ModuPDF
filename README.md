# ModuPDF 4.4

Aplicacao para organizar, otimizar, converter, editar e proteger documentos PDF.
Usuarios da aplicacao nao precisam de Git. O frontend utiliza bibliotecas locais,
inclusive PDF.js e Lucide, sem depender de CDN durante o uso.
Interface com navegacao lateral no desktop, abas no celular e ferramentas
expansiveis. Apenas o formulario escolhido permanece aberto em cada categoria.

## Windows

Com Python 3.12 instalado, execute na pasta do projeto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Start-ModuPDF.ps1
```

Abra http://127.0.0.1:8768. O script utiliza o interpretador do ambiente virtual,
sem exigir ativacao. Para escolher outra porta, passe `-Port 8770`.

## Recursos

| Categoria | Operacoes |
| --- | --- |
| Organizar | Multiplos PDFs, miniaturas, selecao multipla, arrastar paginas, mover, duplicar, girar, excluir, desfazer/refazer, salvar, juntar, dividir em ZIP, extrair e remover |
| Otimizar | Compressao com meta e medidas reais, reparacao, OCR e imagens digitalizadas |
| Converter | JPG/PNG/TIFF/WebP para PDF, PDF para imagens, Office/PDF, HTML estatico, Word editavel, extracao de tabelas Excel, slides PowerPoint em imagem, PDF/A |
| Editar | Substituir ou excluir texto existente, numeracao, marca d'agua diagonal, recorte, inserir texto/imagem/retangulo, criar campos e preencher formularios |
| Seguranca | AES-256, desbloqueio com senha, assinatura criptografica P12/PFX, ocultacao permanente e comparacao visual |

OCR, Office para PDF e PDF/A exigem motores externos. O contêiner inclui
LibreOffice, Ghostscript, qpdf, Tesseract (por/eng/spa) e OCRmyPDF. Na execucao
Python local, recursos sem motor instalado ficam desabilitados. Solicitar OCR
explicitamente nunca produz um sucesso sem OCR.

Conversoes tem limites reais: Word pode precisar de revisao do layout; Excel
extrai tabelas detectadas; PowerPoint preserva cada pagina como imagem, sem
editar os elementos internos. HTML converte texto e CSS estatico sem executar
scripts ou buscar imagens/recursos externos. PDF/A e produzido pelo OCRmyPDF;
quando veraPDF nao existe, a interface informa a ausencia de validacao independente.
Assinar nao implica confianca publica no certificado e nao adiciona carimbo de tempo.
O editor de texto existente remove o trecho original e grava a substituicao na
mesma posicao, preservando cor, estilo aproximado e o conteudo visual de fundo.
Ele aceita texto horizontal e selecionavel. Digitalizacoes precisam de OCR;
texto inclinado, vertical ou convertido em curvas permanece indisponivel.

## Docker local

Requer Docker e Compose 2.24.4 ou superior:

```sh
docker compose up -d --build
curl --fail http://127.0.0.1:8080/api/health
```

Abra http://127.0.0.1:8080. Apenas Nginx publica porta; FastAPI permanece na
rede interna. O contêiner executa como usuario sem privilegios, com raiz somente
leitura, temporarios em tmpfs, limite de memoria e um trabalho simultaneo por padrao.

## GitHub Pages

Publique o conteudo de `frontend/`. Caminhos de scripts, logo, worker, fontes e
recursos sao relativos e funcionam sob `/ModuPDF/`. Configure
`frontend/assets/config.js` com `apiBase: "https://api.seu-dominio.com"`.
Tambem e possivel escolher o servidor no controle de conexao do cabecalho.
O frontend nao armazena certificados, senhas nem conteudo dos documentos.
Permita a origem `https://shazam006.github.io` no CORS do backend.

Sem API, o modo local preserva organizar, juntar, extrair/dividir, remover, girar,
reparar, numerar, marca d'agua, recortar, converter JPG/PNG e exportar imagens.
A compressao local apenas otimiza a estrutura, sem rasterizar texto ou vetores
e sem garantir a meta. Perfis de reducao de imagens exigem API. Operacoes
avancadas permanecem desabilitadas ate conectar um servidor com os motores.
O modo local usa pdf-lib 1.17.1 e JSZip 3.10.1, hospedados junto ao frontend.
Ao copiar paginas no modo local, confira formularios e assinaturas existentes.

## Privacidade e limites

- `MAX_UPLOAD_MB=100` limita o total de arquivos de cada operacao, inclusive multiplos PDFs.
- Extensao, MIME, assinatura PDF, estruturas Office e imagens sao verificados.
- `MAX_PAGES=500`, limite de pixels e `MAX_CONCURRENT_JOBS=1` reduzem o consumo de memoria.
- Cada POST tem um diretorio isolado. Entrada, intermediarios e saida sao removidos em `finally`, depois da transmissao do resultado, inclusive em erro.
- Limpeza inicial e `/api/system/cleanup` removem residuos antigos, preservando trabalhos ativos.
- Conversao Word, LibreOffice e OCR executam em subprocessos com timeout configuravel.
- Logs proprios registram endpoint, duracao, bytes, status, tipo de erro e identificador; nao registram texto, senhas ou certificados.
- Segredos, certificados e arquivos de usuarios estao excluidos de Git e do contexto Docker.

Se alterar `MAX_UPLOAD_MB`, ajuste tambem `client_max_body_size` nos arquivos
Nginx. O padrao de 101 MB admite 100 MB de arquivos mais o multipart.
Uma EC2 de 2 GiB pode precisar de upgrade para OCR/Office de documentos complexos.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes verificam conteudo e geometria do PDF, ordem, copias com rotacoes
independentes, arquivos invalidos, limites, limpeza, formularios e validade
criptografica. Testes de motores reais sao ignorados quando o motor esta ausente.

Com o servidor em http://127.0.0.1:8768, Node e Playwright instalados:

```sh
npm install
npx playwright install chromium
npm run test:ui
```

`MODUPDF_URL`, `MODUPDF_PYTHON` e `CHROME_PATH` permitem ajustar servidor,
interpretador e navegador. O teste usa uploads, selecao, drag/drop, historico e
downloads reais, reabre as saidas e captura telas desktop/mobile em `artifacts/ui`.
Fixtures e certificados de teste ficam em `artifacts/`, nunca no repositorio.

Para testar o modo estatico, sirva `frontend/` na porta 8769 e execute
`npm run test:static` depois do teste de API, que gera as fixtures. Ajuste
`MODUPDF_STATIC_URL` para outra porta. O teste estatico processa arquivos
sem nenhum POST para a API e verifica downloads e recursos indisponiveis.

Para verificar os motores no ambiente de producao isolado:

```sh
docker build --target test -t modupdf-test .
docker run --rm --network none --tmpfs /tmp:size=512m modupdf-test
```

## AWS

Consulte [deploy/aws/README.md](deploy/aws/README.md). A arquitetura atual e EC2
exclusiva + Docker + Nginx + HTTPS. Criacao de recursos, dominio, certificado e
implantacao ainda exigem acesso a conta AWS e nao fazem parte da execucao local.
GeoVida deve permanecer completamente separado.
