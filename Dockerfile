FROM python:3.9-slim

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Criar diretório para os dados
RUN mkdir -p /app/data

# Copiar código
COPY app/ .

# Porta para Flask
EXPOSE 8080

# Comando para iniciar a aplicação
CMD ["python", "main.py"]