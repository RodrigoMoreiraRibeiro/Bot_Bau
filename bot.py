import os
import json
import base64
import discord
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask
from datetime import datetime

# Configurações do Flask para manter o container ativo no Cloud Run
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot está rodando!", 200

# ======== CONFIGURAÇÕES ======== #
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GSPREAD_CREDENTIALS_BASE64 = os.getenv("GOOGLE_CREDENTIALS")
SHEET_NAME = os.getenv("SHEET_NAME")  # Nome da planilha no Google Sheets
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))  # ID do canal do Discord

# Decodifica as credenciais do Google Sheets
creds_json = json.loads(base64.b64decode(GSPREAD_CREDENTIALS_BASE64))
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_json,
    ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME)

# Conectar ao Discord
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
client = discord.Client(intents=intents)

# ======== FUNÇÃO PARA OBTER A ABA CORRETA ======== #
def obter_aba_do_dia():
    """Retorna a aba correta da planilha com base no dia da semana."""
    DIA_ABA_MAP = {
        "Monday": "SEG/TER",
        "Tuesday": "SEG/TER",
        "Wednesday": "QUA/QUI",
        "Thursday": "QUA/QUI",
        "Friday": "SEX/SAB",
        "Saturday": "SEX/SAB",
        "Sunday": "DOM"
    }
    hoje = datetime.today().strftime("%A")  # Nome do dia da semana em inglês
    return DIA_ABA_MAP.get(hoje, "DOM")  # Default para "DOM" se der erro

# ======== FUNÇÃO PARA PROCESSAR MENSAGEM ======== #
def process_message(message):
    lines = message.content.split("\n")
    passaporte = None
    quantidade = 0

    for line in lines:
        if line.startswith("Passaporte:"):
            passaporte = line.split(":")[1].strip()
        elif "Guardou:" in line and "Alumínio" in line:
            quantidade = int(line.split("x")[0].split(":")[1].strip())

    if passaporte and quantidade > 0:
        update_sheet(passaporte, quantidade)

# ======== FUNÇÃO PARA ATUALIZAR PLANILHA ======== #
def update_sheet(passaporte, quantidade):
    aba_nome = obter_aba_do_dia()
    aba = sheet.worksheet(aba_nome)

    # Busca o passaporte na planilha
    cell = aba.find(str(passaporte))

    if cell:
        row = cell.row
        col = 5  # Coluna onde está o Alumínio
        aba.update_cell(row, col, int(aba.cell(row, col).value) + quantidade)
    else:
        aba.append_row([passaporte, "", "", "", quantidade])  # Adiciona o passaporte na coluna 1 e Alumínio na coluna 5

    print(f"✅ Atualizado: {passaporte} adicionou {quantidade} Alumínio em {aba_nome}")

# ======== EVENTO QUANDO UMA MENSAGEM É ENVIADA NO CANAL ======== #
@client.event
async def on_message(message):
    if message.channel.id == CHANNEL_ID and not message.author.bot:
        process_message(message)

# ======== INICIAR O BOT ======== #
async def start_bot():
    await client.start(DISCORD_TOKEN)

# Criar a tarefa assíncrona
import asyncio
loop = asyncio.get_event_loop()
loop.create_task(start_bot())

# Mantém o container ativo no Cloud Run
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
