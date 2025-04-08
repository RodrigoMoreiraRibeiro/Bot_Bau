import os
import json
import base64
import discord
import gspread
import asyncio
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask

# Configuração do Flask para manter o container ativo no Cloud Run
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot está rodando!", 200

# ======== CONFIGURAÇÕES ======== #

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GSPREAD_CREDENTIALS_BASE64 = os.getenv("GOOGLE_CREDENTIALS")
SHEET_NAME = os.getenv("SHEET_NAME")  # Nome da planilha no Google Sheets

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
    from datetime import datetime

    dias = {
        0: "SEG/TER", 1: "SEG/TER",
        2: "QUA/QUI", 3: "QUA/QUI",
        4: "SEX/SAB", 5: "SEX/SAB",
        6: "DOM"
    }

    hoje = datetime.today().weekday()
    aba_nome = dias[hoje]
    aba = sheet.worksheet(aba_nome)

    # Busca o passaporte na planilha
    cell = aba.find(str(passaporte))

    if cell:
        row = cell.row
        col = 5  # Coluna onde está o Alumínio
        aba.update_cell(row, col, int(aba.cell(row, col).value) + quantidade)
    else:
        aba.append_row([passaporte, quantidade])

    print(f"Atualizado: {passaporte} adicionou {quantidade} Alumínio em {aba_nome}")

# ======== EVENTO QUANDO UMA MENSAGEM É ENVIADA NO CANAL ======== #
@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')

@client.event
async def on_message(message):
    if not message.author.bot:
        process_message(message)

# ======== INICIAR O BOT E O FLASK EM PARALELO ======== #
def run_discord_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(client.start(DISCORD_TOKEN))

if __name__ == "__main__":
    from threading import Thread

    # Rodar o bot do Discord em uma thread separada
    discord_thread = Thread(target=run_discord_bot)
    discord_thread.start()

    # Rodar o Flask na thread principal
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
