import os
import discord
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Configurar Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# Abrir a planilha
SHEET_NAME = "Teste de Bot  PLANILHA DE CONTROLE FARM"  # Substitua pelo nome da planilha
spreadsheet = client.open(SHEET_NAME)

# Configurar o bot do Discord
intents = discord.Intents.default()
intents.messages = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'✅ Bot conectado como {client.user}')

@client.event
async def on_message(message):
    if message.author.bot:
        return
    
    # Verifica se a mensagem tem "Guardou" e "Alumínio"
    if "Guardou" in message.content and "Alumínio" in message.content:
        lines = message.content.split("\n")
        passport_id = None
        quantity = 0

        for line in lines:
            if line.startswith("Passaporte:"):
                passport_id = line.split(":")[1].strip()
            elif "Guardou" in line and "Alumínio" in line:
                quantity = int(line.split(" ")[1].replace("x", "").strip())

        if passport_id and quantity > 0:
            # Identificar o dia da semana e a aba correta
            from datetime import datetime
            weekdays = ["SEG/TER", "QUA/QUI", "SEX/SAB"]
            today = datetime.today().weekday()
            sheet_name = weekdays[today // 2]  # Cada aba cobre 2 dias

            sheet = spreadsheet.worksheet(sheet_name)

            # Verificar se o passaporte já tem um registro e somar valores
            cell = sheet.find(passport_id)
            if cell:
                current_value = int(sheet.cell(cell.row, 2).value or 0)
                new_value = current_value + quantity
                sheet.update_cell(cell.row, 2, new_value)
            else:
                sheet.append_row([passport_id, quantity])

            await message.channel.send(f"✅ Atualizado: Passaporte {passport_id} guardou {quantity}x Alumínio.")

# Pegar o token do ambiente
TOKEN = os.getenv("TOKEN")
client.run(TOKEN)
