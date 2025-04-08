import os
import json
import base64
import discord
import gspread
import asyncio
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask
from datetime import datetime
from threading import Thread

# ======================== FLASK (Mantém o Container Ativo no Cloud Run) ======================== #
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot está rodando!", 200

# ======================== CONFIGURAÇÕES ======================== #

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
SHEET_NAME = os.getenv("SHEET_NAME")  # Nome da planilha do Google Sheets

# Decodifica as credenciais do Google Sheets
creds_json = json.loads(base64.b64decode(GOOGLE_CREDENTIALS))
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_json,
    ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME)

# Testa acesso à planilha
SHEET_NAME = os.getenv("SHEET_NAME")  # Nome da planilha
sheet = client.open(SHEET_NAME)
print("✅ Conectado à planilha:", sheet.title)

# Testa acesso a uma aba específica
worksheet = sheet.worksheet("FARM SEG E TER")
print("✅ Conectado à aba:", worksheet.title)

# Testa escrita
worksheet.append_row(["Teste", "123"])
print("✅ Escrita na planilha realizada com sucesso!")

# Configurar Intents do Discord
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
client = discord.Client(intents=intents)

# ======================== FUNÇÃO PARA ATUALIZAR A PLANILHA ======================== #

# Mapear abas e colunas conforme o dia da semana
dias = {
    0: ("FARM SEG E TER", 5),   # Segunda -> Coluna 5
    1: ("FARM SEG E TER", 14),  # Terça   -> Coluna 14
    2: ("FARM QUA E QUI", 5),   # Quarta  -> Coluna 5
    3: ("FARM QUA E QUI", 14),  # Quinta  -> Coluna 14
    4: ("FARM SEX E SAB", 5),   # Sexta   -> Coluna 5
    5: ("FARM SEX E SAB", 14),  # Sábado  -> Coluna 14
    6: ("FARM DOM", 5)          # Domingo -> Sempre Coluna 5
}

def update_sheet(passaporte, quantidade):
    hoje = datetime.today().weekday()
    aba_nome, coluna = dias[hoje]  # Define qual aba e qual coluna usar
    aba = sheet.worksheet(aba_nome)

    # Buscar o passaporte na planilha
    cell = aba.find(str(passaporte))

    if cell:
        row = cell.row
        aba.update_cell(row, coluna, int(aba.cell(row, coluna).value or 0) + quantidade)
    else:
        aba.append_row([passaporte] + [""] * (coluna - 2) + [quantidade])

    print(f"✅ Atualizado: {passaporte} adicionou {quantidade} Alumínio em {aba_nome}, coluna {coluna}")

# ======================== FUNÇÃO PARA PROCESSAR MENSAGEM ======================== #

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

# ======================== EVENTOS DO DISCORD ======================== #

@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')

@client.event
async def on_message(message):
    print(f"📩 Mensagem recebida: {message.content}")
    if not message.author.bot:
        process_message(message)

# ======================== INICIAR O BOT E O FLASK EM PARALELO ======================== #

def run_discord_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(client.start(DISCORD_TOKEN))

if __name__ == "__main__":
    # Rodar o bot do Discord em uma thread separada
    discord_thread = Thread(target=run_discord_bot)
    discord_thread.start()

    # Rodar o Flask na thread principal
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
