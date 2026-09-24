# ModuPDF 4.3

- Nova identidade ModuPDF aplicada ao site, API, Docker, scripts, testes e documentacao.
- Novo simbolo modular com pagina, letra M e paleta verde, grafite e ocre.
- Navegacao de cinco abas acessivel, responsiva e com textos UTF-8 corrigidos.
- Organizador com selecao multipla, insercao drag/drop, controles alternativos,
  duplicacao, rotacao independente, historico real e salvamento na ordem visual.
- Assets relativos, splash, logo com fallback e PDF.js/Lucide locais.
- Conexao configuravel com API, estados de processamento/erro/download e recursos
  desabilitados quando o motor correspondente nao existe.
- Compressao com meta aproximada, tamanhos e reducao reais, sem rasterizar texto
  ou vetores; nunca entrega um arquivo maior que o original.
- Implementados HTML estatico, PDF/Office, editor de adicoes, formularios,
  assinatura P12/PFX, ocultacao permanente e comparacao visual.
- Corrigida marca d'agua diagonal e envio do checkbox OCR.
- Uploads validados/limitados, armazenamento isolado, cleanup apos resposta,
  CORS configuravel, timeouts e concorrencia limitada.
- Docker non-root com motores completos, Compose e Nginx/HTTPS para EC2 exclusiva.
- Testes de conteudo, assinatura, formularios, limites, motores reais e browser.
- Adicoes de texto/imagem mantem a orientacao visual em paginas ja giradas.
- Comparacao alinha paginas de tamanhos diferentes em quadros de mesma escala.
- Deteccao de motores no ambiente virtual e caminhos de dependencias no Windows.
- Limite de resolucao aplicado antes de processar imagens enviadas ou inseridas.
- Upload do organizador com botao unico e operacao por teclado verificada.
- Interface com navegacao lateral, hierarquia visual e formularios expansiveis.
- Preservado modo local para ferramentas simples na publicacao GitHub Pages.
- Testes remotos reconciliados; CI verifica API, frontend estatico e motores.
- Removidos workflows obsoletos que reescreviam automaticamente o HTML.
- P12/PFX aceita MIME padrao e legado; assinatura validada no browser Linux.
- Publicacao GitHub Pages verificada com processamento e downloads reais.

Referencia preservada: correcao de navegacao do commit
53642b3ca42b3263378cc1db8e005c9d7c382c3c. A versao local foi reconciliada com
o comportamento dessa correcao, mantendo a marca e os assets locais.
