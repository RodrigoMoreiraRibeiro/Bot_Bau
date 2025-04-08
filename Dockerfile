# Usa uma imagem oficial do Python
FROM python:3.10

# Define o diretório de trabalho no container
WORKDIR /app

# Copia os arquivos do projeto para o container
COPY . .

# Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Define a variável de ambiente para a porta do Flask
ENV PORT=8080

# Expõe a porta 8080
EXPOSE 8080

# Comando para iniciar o Flask e o bot do Discord
CMD ["python", "bot.py"]

