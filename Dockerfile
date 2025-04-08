# Usar imagem base do Python
FROM python:3.11

# Definir diretório de trabalho
WORKDIR /app

# Copiar arquivos para o contêiner
COPY bot.py requirements.txt ./

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Definir variável de ambiente padrão (pode ser sobrescrita)
ENV GOOGLE_CREDENTIALS="{}"

# Executar o bot
CMD ["python", "bot.py"]
