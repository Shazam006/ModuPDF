# Evolucao AWS - ModuPDF

1. Homologar localmente endpoints, uploads, download, organizador e conversoes.
2. Criar EC2 exclusiva modupdf em sa-east-1; manter GeoVida separado.
3. Executar Docker e Nginx; homologar health, limites, compressao, OCR e Office.
4. Configurar dominio, certificado valido e HTTPS; conectar frontend e CORS.
5. Executar testes com motores reais, monitorar memoria e definir upgrade.
6. Automatizar entrega de imagem via GitHub Actions e credenciais federadas IAM.
7. Conforme demanda: fila de trabalhos, workers independentes e armazenamento
   temporario S3 com expiracao, sem mudar contratos das ferramentas.

O MVP nao depende de Amplify, App Runner, RDS, Redis ou Kubernetes.
Contas, planos e cobranca sao etapas posteriores a homologacao do processamento.
