# Implantacao independente do ModuPDF

Este roteiro prepara uma nova infraestrutura. Nao reutilize nem altere
`geovida_sp`, banco, volumes, IP, arquivos ou security groups GeoVida.

## Nova instancia

Na conta AWS escolhida: nome `modupdf`, regiao `sa-east-1`, Amazon Linux 2023,
x86_64, t3.small, 30 GiB EBS gp3 e IPv4 publico. Use IAM Role com permissoes
minimas quando integrar logs/ECR; nunca coloque chaves AWS em arquivos do projeto.

Crie um security group exclusivo: SSH 22 restrito ao IP administrativo;
HTTP 80 e HTTPS 443 publicos. Nao abra 8000. Prefira Session Manager quando
ja estiver configurado para esta nova instancia.

Instale Docker e Compose pelo procedimento oficial compativel com Amazon Linux.
Requer Compose >=2.24.4 por causa do override de portas. Clone o repositorio no
servidor administrativo; Git nao e requisito para usuarios do produto.

## Homologacao e HTTPS

```sh
docker compose up -d --build
curl --fail http://127.0.0.1:8080/api/health
docker compose logs --tail=100 api
```

Esta primeira configuracao HTTP vincula a porta 8080 apenas a localhost.
Homologue via tunel SSH, sem abrir essa porta ao publico. Configure DNS de um
dominio proprio e obtenha um certificado valido, por exemplo com DNS challenge.
Coloque copias de `fullchain.pem` e `privkey.pem` em `deploy/certs/`, sem versionar.
Configure renovacao do certificado e recarga do Nginx.

Crie `.env` a partir de `.env.example`, com a origem real do frontend em CORS.
Nao e necessario guardar senhas ou certificados de assinatura nesse arquivo.

```sh
docker compose -f compose.yaml -f compose.production.yaml up -d --build
curl --fail https://SEU-DOMINIO/api/health
```

A configuracao de producao substitui a publicacao local por 80/443; HTTP
redireciona para HTTPS. A porta FastAPI fica interna. Certificados TLS validos
sao obrigatorios antes de usar este comando em producao.

## Aceite

Execute testes do alvo Docker `test`, envie/baixe documentos pelo frontend,
confira compressao com meta, OCR em portugues, Office, CORS e expiracao de
arquivos. Teste interrupcao do cliente e erros de conversao. Monitore RAM,
CPU e espaco temporario. Mantenha um trabalho pesado simultaneo inicialmente.
Se faltar RAM, aumente para t3.medium ou superior antes de ampliar concorrencia.

O workflow prepara e verifica imagens; nao provisiona EC2 nem publica
automaticamente sem configurar destino e autenticacao da conta AWS.
