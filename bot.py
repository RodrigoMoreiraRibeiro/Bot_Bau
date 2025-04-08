import discord
import os
import json
import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")

# Carregar credenciais do Google Cloud a partir da variável de ambiente
credentials_info = json.loads(CREDENTIALS_JSON)
credentials = service_account.Credentials.from_service_account_info(credentials_info)
service = build("sheets", "v4", credentials=credentials)

# Configuração do bot
intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Bot {client.user} está online!')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if "Guardou" in message.content:
        try:
            lines = message.content.split("\n")
            passaporte = lines[0].split(":")[1].strip()
            quantidade = int(lines[1].split("x")[0].split(":")[1].strip())

            # Atualizar planilha do Google Sheets
            sheet = service.spreadsheets()
            SPREADSHEET_ID = "SUA_PLANILHA_ID"
            RANGE_NAME = "SEG/TER!A1:C100"

            values = [[passaporte, "Alumínio", quantidade]]
            body = {"values": values}

            sheet.values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME,
                valueInputOption="RAW",
                body=body
            ).execute()

            await message.channel.send(f"Registrado: {quantidade}x Alumínio para Passaporte {passaporte}")
        except Exception as e:
            print(f"Erro: {e}")

client.run(TOKEN)
