# Usa uma imagem Python leve
FROM python:3.9-slim

# Define diretório de trabalho
WORKDIR /app

# Copia os arquivos
COPY bot.py .  
COPY requirements.txt .

# Instala dependências
RUN pip install --no-cache-dir -r requirements.txt

# Expor a porta 8080 para o Cloud Run
EXPOSE 8080

# Executar o bot
CMD ["python", "bot.py"]
