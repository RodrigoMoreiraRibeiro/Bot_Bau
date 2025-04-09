# Aluminio Bot - Documentação

## Visão Geral

O Aluminio Bot é um bot Discord desenvolvido para gerenciar e rastrear o armazenamento e retirada de "Alumínio" para membros da "PASTELARIA DO CHINA" em um jogo. O bot interage com o Discord para receber comandos e com o Google Sheets para armazenar e consultar dados.

## Funcionalidades

- Registro de depósito de Alumínio por passaporte de jogador
- Registro de retirada de Alumínio por passaporte de jogador
- Controle de registros por dia da semana (com diferentes abas para diferentes dias)
- Reset automático dos valores aos domingos
- Sistema de backup para operações pendentes em caso de falha de conexão
- Healthchecks para monitoramento da aplicação

## Arquitetura

O sistema é composto por:

1. **Cliente Discord**: Interface para interação com os usuários
2. **Google Sheets**: Base de dados para armazenamento dos registros
3. **Flask API**: Servidor para healthchecks e manter o container ativo
4. **Sistema de backup**: Armazenamento local de operações pendentes

## Requisitos

- Python 3.9+
- Discord.py 2.3.2
- gspread 5.10.0
- oauth2client 4.1.3
- Flask 2.3.3
- pytz 2023.3
- python-dotenv 1.0.0

## Configuração

### Variáveis de Ambiente

O sistema utiliza as seguintes variáveis de ambiente:

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `DISCORD_TOKEN` | Token de acesso à API do Discord | Sim |
| `GOOGLE_CREDENTIALS` | Credenciais do Google Service Account (base64) | Sim |
| `SHEET_NAME` | Nome da planilha do Google Sheets | Sim |
| `PAINEL_CONTROLE` | Nome da aba do painel de controle (default: "PAINEL DE CONTROLE") | Não |
| `DATA_DIR` | Diretório para armazenamento de dados (default: "/app/data") | Não |

### Estrutura da Planilha

A planilha do Google Sheets deve conter as seguintes abas:

- `FARM SEG E TER`: Registros de segunda e terça-feira
- `FARM QUR E QUI`: Registros de quarta e quinta-feira 
- `FARM SEX E SÁB`: Registros de sexta e sábado
- `FARM DOM`: Registros de domingo (não utilizados ativamente)
- `PAINEL DE CONTROLE`: Painel central para controle de metas

## Comandos

### Comandos de Usuário

| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| Registrar Alumínio | Registra o depósito de Alumínio | `Passaporte: 123 Guardou: 50x Alumínio` |
| Retirar Alumínio | Registra a retirada de Alumínio | `Passaporte: 123 Retirou: 50x Alumínio` |
| `!ajuda` ou `!help` | Mostra a mensagem de ajuda | `!ajuda` |
| `!add` | Mostra um template para adicionar Alumínio | `!add` |

### Comandos Administrativos

| Comando | Descrição | Permissão |
|---------|-----------|-----------|
| `!reset` | Força o reset dominical dos valores | Administrador |

## Operação

### Ciclo Semanal

- **Segunda a Sábado**: Registros normais de atividade
- **Domingo**: Não aceita registros e realiza o reset para a próxima semana após 12h

### Processamento de Mensagens

1. Bot recebe mensagem no Discord
2. Extrai passaporte, quantidade e operação usando expressões regulares
3. Atualiza a planilha na aba e coluna correspondente ao dia da semana
4. Responde ao usuário com confirmação da operação

### Backup e Recuperação

Em caso de falha de conexão com o Google Sheets:
1. A operação é salva em um arquivo CSV local
2. Um processo periódico tenta processar as operações pendentes
3. Após 5 tentativas sem sucesso, a operação é abandonada

## Implantação no GCP via GitOps

O projeto é implantado continuamente no Google Cloud Platform usando o método GitOps. Abaixo está o fluxo de CI/CD:

### Fluxo de Implantação

1. O código é enviado para o repositório Git
2. O Cloud Build é acionado automaticamente
3. A imagem Docker é construída usando o Dockerfile fornecido
4. A imagem é armazenada no Container Registry
5. O Cloud Run Service é atualizado com a nova imagem

### Dockerfile

```dockerfile
# Imagem base oficial do Python
FROM python:3.9-slim
# Definir variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data
# Instalar dependências do sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
# Criar diretório de trabalho
WORKDIR /usr/src/app
# Criar diretório para dados persistentes
RUN mkdir -p /app/data
# Copiar requisitos e instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copiar código fonte
COPY ./app ./app
# Expor a porta usada pelo Flask
EXPOSE 8080
# Comando para iniciar a aplicação
CMD ["python", "app/main.py"]
```

### Configuração do Cloud Build

Crie um arquivo `cloudbuild.yaml` na raiz do projeto:

```yaml
steps:
  # Construir a imagem Docker
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/aluminio-bot:$COMMIT_SHA', '.']
  
  # Enviar a imagem para o Container Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/aluminio-bot:$COMMIT_SHA']
  
  # Implantar no Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'aluminio-bot'
      - '--image=gcr.io/$PROJECT_ID/aluminio-bot:$COMMIT_SHA'
      - '--region=us-central1'
      - '--platform=managed'
      - '--allow-unauthenticated'

# Imagens que serão geradas
images:
  - 'gcr.io/$PROJECT_ID/aluminio-bot:$COMMIT_SHA'
```

### Configuração de Segredos

Para gerenciar os segredos (variáveis de ambiente sensíveis), use o Secret Manager do GCP:

1. Crie os segredos no Secret Manager:
   ```bash
   gcloud secrets create discord-token --replication-policy="automatic"
   gcloud secrets create google-credentials --replication-policy="automatic"
   gcloud secrets create sheet-name --replication-policy="automatic"
   ```

2. Adicione os valores aos segredos:
   ```bash
   echo -n "seu-token-discord" | gcloud secrets versions add discord-token --data-file=-
   echo -n "credenciais-base64" | gcloud secrets versions add google-credentials --data-file=-
   echo -n "nome-da-planilha" | gcloud secrets versions add sheet-name --data-file=-
   ```

3. Dê permissão à conta de serviço do Cloud Run para acessar os segredos:
   ```bash
   gcloud secrets add-iam-policy-binding discord-token \
     --member=serviceAccount:service-PROJECT_NUMBER@gcp-sa-cloudrun.iam.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor
   
   # Repita para os outros segredos
   ```

4. Modifique o `cloudbuild.yaml` para usar os segredos:
   ```yaml
   args:
     - 'run'
     - 'deploy'
     - 'aluminio-bot'
     - '--image=gcr.io/$PROJECT_ID/aluminio-bot:$COMMIT_SHA'
     - '--region=us-central1'
     - '--platform=managed'
     - '--allow-unauthenticated'
     - '--set-secrets=DISCORD_TOKEN=discord-token:latest,GOOGLE_CREDENTIALS=google-credentials:latest,SHEET_NAME=sheet-name:latest'
   ```

## Monitoramento e Manutenção

### Endpoints de Healthcheck

- `/`: Retorna "✅ Bot está rodando!" se o servidor estiver funcionando
- `/health`: Retorna um JSON com detalhes do status do bot, incluindo:
  - Status da conexão com o Discord
  - Status da conexão com o Google Sheets
  - Timestamp atual
  - Informações de ambiente

### Logs

O sistema utiliza o módulo `logging` do Python para registrar eventos com diferentes níveis:

- `INFO`: Operações normais e inicialização
- `WARNING`: Problemas não-críticos, como reconexões
- `ERROR`: Falhas em operações específicas
- `CRITICAL`: Falhas que podem comprometer o funcionamento do bot

### Reinicialização

O sistema foi projetado para lidar com reinicializações:
- Operações pendentes são armazenadas em disco
- Conexões são reestabelecidas automaticamente
- O sistema verifica e processa operações pendentes ao iniciar

## Solução de Problemas

### Problemas Comuns

1. **Bot não responde no Discord**
   - Verifique se o token Discord está correto
   - Verifique se o bot tem permissões no canal

2. **Falha ao atualizar a planilha**
   - Verifique se as credenciais do Google estão corretas
   - Verifique se a conta de serviço tem acesso à planilha
   - Verifique se a estrutura da planilha está correta

3. **Container reiniciando constantemente**
   - Verifique os logs no Cloud Run
   - Verifique se as variáveis de ambiente estão configuradas corretamente

### Verificando Logs no GCP

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=aluminio-bot" --limit=20
```

## Contribuindo

Para contribuir com o desenvolvimento:

1. Clone o repositório
2. Crie um arquivo `.env` com as variáveis de ambiente necessárias
3. Instale as dependências: `pip install -r requirements.txt`
4. Faça suas alterações
5. Envie um pull request
