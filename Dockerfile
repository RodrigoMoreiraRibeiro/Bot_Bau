# Usa a imagem oficial do Python
FROM python:3.10

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia os arquivos do projeto
COPY requirements.txt requirements.txt
COPY bot.py bot.py

# Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta que o Cloud Run usa
EXPOSE 8080

# Comando para rodar o bot
CMD ["python", "bot.py"]
