# ModuPDF 4.3 - Homologacao local

Verificacao original em 17/09/2026 e revalidacao da identidade ModuPDF em
24/09/2026, Windows, Python 3.12 e Chrome headless.

## Resultado

- Backend e codigo frontend: 85 testes passaram; 7 testes de motores externos foram ignorados.
- Navegador com API: 32 verificacoes passaram, sem erros JavaScript.
- Navegador estatico: 18 verificacoes passaram sem nenhum POST para a API.
- Cinco abas verificadas no desktop e em telas de 320, 390 e 768 pixels.
- Dependencias Python: `pip check` sem conflitos.
- Health check: `status: ok`, versao 4.3.
- Diretorio `work/` vazio depois dos uploads, downloads e erros de teste.
- Nova identidade verificada no desktop e no celular, sem quebra de layout.

Os downloads foram reabertos para verificar ordem e numero de paginas,
rotacoes independentes, texto inserido, ocultacao permanente, senhas e valores
canonicos de formularios. A assinatura foi verificada criptograficamente nos
testes do backend, com certificado efemero de teste.

## Melhorias desta retomada

- Texto e imagens inseridos mantem a orientacao visivel de paginas giradas.
- Comparacao usa quadros alinhados ao comparar paginas de tamanhos diferentes.
- Motores do ambiente virtual sao detectados sem exigir sua ativacao.
- Dependencias nativas detectadas ficam no PATH somente dos subprocessos.
- Imagens acima do limite de pixels sao rejeitadas antes do processamento.
- Upload do organizador usa um unico botao acessivel por teclado.
- Navegacao por setas, Home e End e abertura do seletor por Enter verificadas.
- Navegacao lateral no desktop, abas no celular e formularios expansiveis.
- Modo local preserva ferramentas simples publicadas no GitHub Pages.
- Testes atuais do GitHub reconciliados com a versao local.
- CI valida API, modo estatico e motores Docker, sem alterar o codigo fonte.

## Limites da validacao

Ghostscript foi detectado nesta maquina. LibreOffice, Tesseract, OCRmyPDF, qpdf
e veraPDF nao foram detectados. OCR, Office para PDF e PDF/A permanecem
indisponiveis na execucao Python local, sem simular sucesso. PDF para Word,
Excel e PowerPoint foram processados; as limitacoes de fidelidade continuam
documentadas no README.

Docker nao esta disponivel nesta maquina. O Dockerfile, Compose, Nginx e o
workflow de testes com motores reais foram preparados, mas nao executados aqui.
Os sete testes ignorados cobrem OCR em por/eng/spa, Office DOCX/XLSX/PPTX e PDF/A.

Na CI do GitHub, o job `engines` executou o contêiner: 91 testes passaram,
incluindo os sete testes de motores reais. Apenas a verificacao Node foi
ignorada nesse contêiner; ela pertence ao job separado de frontend.
Execucao: https://github.com/Shazam006/ModuPDF/actions/runs/35284704213.

## Publicacao

PR #4 integrada na `main`, commit de codigo
`5896c3e8b396442eed234fecbc68367fef22a840`.
GitHub Pages concluiu a publicacao com sucesso. O site publico passou nas
18 verificacoes estaticas, incluindo ordem e rotacao dos downloads, texto e
vetores preservados, imagens nao vazias e interface mobile sem overflow.
Site: https://shazam006.github.io/ModuPDF/.

Operacoes avancadas ainda dependem de API com os motores. Publicar o frontend
nao implanta backend AWS nem HTTPS/Nginx da infraestrutura exclusiva.

Nao houve implantacao na AWS nesta retomada.
Nenhum recurso GeoVida foi alterado. A homologacao de producao ainda exige
Docker, EC2 exclusiva do ModuPDF, dominio, HTTPS e testes com motores reais.

## Continuar

Para retomar localmente, execute `Start-ModuPDF.ps1` na pasta do projeto.
Endereco padrao: http://127.0.0.1:8768.

As capturas, resultados do navegador e arquivos de teste ficam em
`artifacts/ui/`, excluido do versionamento. Os comandos de testes e de
homologacao Docker estao no README; o roteiro AWS esta em `deploy/aws/README.md`.
