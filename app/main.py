import os
import json
import base64
import discord
import gspread
import asyncio
import logging
import signal
import re
import csv
import random
import time
import pytz
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, jsonify
from datetime import datetime, timezone, timedelta
from threading import Thread

# ======================== Configurar Logging ======================== #
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('aluminio-bot')

# ======================== FLASK (Mantém o Container Ativo no Cloud Run) ======================== #
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot está rodando!", 200

@app.route('/health')
def health():
    """Endpoint para verificação de saúde do container"""
    status = {
        "discord_connected": discord_client.is_ready() if discord_client else False,
        "sheets_connected": sheet is not None,
        "timestamp": datetime.now().isoformat()
    }
    
    if all([status["discord_connected"], status["sheets_connected"]]):
        return jsonify(status), 200
    else:
        return jsonify(status), 503  # Service Unavailable

# ======================== CONFIGURAÇÕES ======================== #

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
SHEET_NAME = os.getenv("SHEET_NAME")  # Nome da planilha do Google Sheets
PAINEL_CONTROLE = os.getenv("PAINEL_CONTROLE", "PAINEL DE CONTROLE")  # Nome da aba do painel de controle

# Define o diretório de dados com base no ambiente
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

# Garante que o diretório existe
os.makedirs(DATA_DIR, exist_ok=True)

# Decodifica as credenciais do Google Sheets
creds_json = json.loads(base64.b64decode(GOOGLE_CREDENTIALS))

# Variáveis globais
client = None
sheet = None

# ======================== FUNÇÕES DE CONEXÃO COM GOOGLE SHEETS ======================== #

def update_with_exponential_backoff(func, max_retries=5):
    """Executa uma função com retry exponencial"""
    retries = 0
    while retries < max_retries:
        try:
            return func()
        except (gspread.exceptions.APIError, gspread.exceptions.GSpreadException) as e:
            wait_time = (2 ** retries) + random.uniform(0, 1)
            retries += 1
            if retries < max_retries:
                logger.warning(f"⚠️ Tentativa {retries}/{max_retries} falhou. Esperando {wait_time:.2f}s antes de tentar novamente.")
                time.sleep(wait_time)
            else:
                raise e

def connect_to_sheets():
    global client, sheet
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_json,
            ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        logger.info("✅ Conectado à planilha: %s", sheet.title)
        return sheet
    except Exception as e:
        logger.error("❌ Erro ao conectar com Google Sheets: %s", str(e))
        raise

def reconnect_sheets():
    global client, sheet
    try:
        logger.info("🔄 Reconectando ao Google Sheets...")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_json,
            ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        logger.info("✅ Reconectado à planilha: %s", sheet.title)
        return sheet
    except Exception as e:
        logger.error("❌ Erro ao reconectar com Google Sheets: %s", str(e))
        return None

# Primeira conexão ao iniciar
# connect_to_sheets()

# ======================== FUNÇÃO PARA EXTRAIR DADOS DA MENSAGEM ======================== #

def extract_data(message_text):
    passaporte = None
    quantidade = 0
    operacao = "guardar"  # Operação padrão é guardar
    
    # Normaliza o texto removendo caracteres especiais, transformando em minúsculas
    normalized_text = re.sub(r'[^\w\s:x]', '', message_text.lower())
    
    # Verificar se é uma operação de retirada
    if "retirou" in normalized_text or "retirar" in normalized_text:
        operacao = "retirar"
    
    # Padrões mais flexíveis para passaporte
    passport_patterns = [
        r"(?:passaporte|pass|id):\s*(\d+)",
        r"(?:passaporte|pass|id)\s+(\d+)",
        r"^(\d+)\s+(?:guardou|guardar|retirou|retirar)"
    ]
    
    for pattern in passport_patterns:
        passport_match = re.search(pattern, normalized_text)
        if passport_match:
            passaporte = passport_match.group(1).strip()
            break
    
    # Padrões mais flexíveis para quantidade
    quantity_patterns = [
        r"(?:guardou|guardar|retirou|retirar):\s*(\d+)x\s*(?:aluminio|al)",
        r"(\d+)x\s*(?:aluminio|al)",
        r"(?:aluminio|al)\s*(\d+)x"
    ]
    
    for pattern in quantity_patterns:
        quantity_match = re.search(pattern, normalized_text)
        if quantity_match:
            quantidade = int(quantity_match.group(1))
            break
    
    # Log para debug
    logger.debug(f"Extração: texto='{message_text}', passaporte={passaporte}, quantidade={quantidade}, operação={operacao}")
    
    return passaporte, quantidade, operacao

# ======================== FUNÇÃO PARA SALVAR OPERAÇÕES PENDENTES ======================== #

def save_pending_update(passaporte, quantidade, operacao="guardar"):
    try:
        filepath = os.path.join(DATA_DIR, "pending_updates.csv")
        file_exists = os.path.exists(filepath)
        
        with open(filepath, "a") as f:
            writer = csv.writer(f)
            if not file_exists:  # Adiciona cabeçalho se for um novo arquivo
                writer.writerow(["passaporte", "quantidade", "operacao", "timestamp", "tentativas"])
            writer.writerow([passaporte, quantidade, operacao, datetime.now().isoformat(), 0])
        logger.info(f"💾 Backup de atualização salvo: {passaporte}, {quantidade}, {operacao}")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao salvar backup: {str(e)}")
        return False

def process_pending_updates():
    try:
        filepath = os.path.join(DATA_DIR, "pending_updates.csv")
        if not os.path.exists(filepath):
            return
            
        pending = []
        processed_indices = []
        
        # Lê o arquivo para memória
        with open(filepath, "r") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # Pula o cabeçalho
            
            for i, row in enumerate(reader):
                if len(row) >= 5:  # passaporte, quantidade, operacao, timestamp, tentativas
                    operacao = row[2] if len(row) > 2 else "guardar"  # Default para compatibilidade
                    pending.append((i, row[0], int(row[1]), operacao, int(row[4])))
                elif len(row) >= 4:  # formato antigo sem operacao
                    pending.append((i, row[0], int(row[1]), "guardar", int(row[3])))
        
        if not pending:
            return
            
        logger.info(f"🔄 Processando {len(pending)} atualizações pendentes")
        
        for i, passaporte, quantidade, operacao, tentativas in pending:
            if tentativas >= 5:  # Limite máximo de tentativas
                logger.warning(f"⚠️ Desistindo após 5 tentativas: {passaporte}, {quantidade}, {operacao}")
                processed_indices.append(i)
                continue
                
            try:
                update_sheet(passaporte, quantidade, operacao=operacao, notify=False)
                processed_indices.append(i)
                logger.info(f"✅ Processada atualização pendente: {passaporte}, {quantidade}, {operacao}")
            except Exception as e:
                logger.error(f"❌ Erro ao processar atualização pendente: {str(e)}")
                
                # Incrementa o contador de tentativas
                idx = pending.index((i, passaporte, quantidade, operacao, tentativas))
                pending[idx] = (i, passaporte, quantidade, operacao, tentativas + 1)
                break
        
        # Atualiza o arquivo removendo itens processados e incrementando tentativas
        if processed_indices:
            updated_rows = []
            with open(filepath, "r") as f:
                reader = csv.reader(f)
                updated_rows.append(next(reader))  # Cabeçalho
                
                for i, row in enumerate(reader):
                    if i not in processed_indices:
                        # Verifica se tentativas precisa ser incrementada
                        for j, p, q, op, t in pending:
                            if j == i:  # Esta é a linha que falhou
                                # Atualiza tentativas dependendo do formato da linha
                                if len(row) >= 5:
                                    row[4] = str(t)  # Formato novo com operacao
                                elif len(row) >= 4:
                                    row[3] = str(t)  # Formato antigo sem operacao
                                break
                        updated_rows.append(row)
            
            with open(filepath, "w") as f:
                writer = csv.writer(f)
                writer.writerows(updated_rows)
                
            logger.info(f"✅ Processadas {len(processed_indices)} de {len(pending)} atualizações pendentes")
    except Exception as e:
        logger.error(f"❌ Erro ao processar atualizações pendentes: {str(e)}")

# ======================== FUNÇÃO AUXILIAR PARA HORÁRIO DE BRASÍLIA ======================== #

def get_brazil_datetime():
    """Retorna o datetime atual no fuso horário de Brasília"""
    tz_brazil = pytz.timezone('America/Sao_Paulo')
    return datetime.now(pytz.UTC).astimezone(tz_brazil)

# ======================== FUNÇÃO PARA ATUALIZAR A PLANILHA ======================== #

# Mapear abas e colunas conforme o dia da semana
dias = {
    0: ("FARM SEG E TER", 5),   # Segunda -> Coluna 5
    1: ("FARM SEG E TER", 14),  # Terça   -> Coluna 14
    2: ("FARM QUR E QUI", 5),   # Quarta  -> Coluna 5
    3: ("FARM QUR E QUI", 14),  # Quinta  -> Coluna 14
    4: ("FARM SEX E SÁB", 5),   # Sexta   -> Coluna 5
    5: ("FARM SEX E SÁB", 14),  # Sábado  -> Coluna 14
    6: ("FARM DOM", 5)          # Domingo -> Coluna 5
}

def update_sheet(passaporte, quantidade, operacao="guardar", notify=True):
    # Validações
    if not str(passaporte).isdigit():
        return "❌ Formato de passaporte inválido (deve conter apenas números)"
    
    if quantidade <= 0 or quantidade > 10000:  # limite razoável
        return "❌ Quantidade inválida"
    
    # Use o horário de Brasília para determinar o dia
    hoje = get_brazil_datetime().weekday()
    
    # Log para debug
    brazil_now = get_brazil_datetime()
    logger.debug(f"🕒 Usando horário de Brasília: {brazil_now.strftime('%Y-%m-%d %H:%M:%S')} (Dia: {hoje})")
    
    # Se for domingo (dia 6), não registra e retorna mensagem
    if hoje == 6:
        return "⚠️ **Atenção:** Aos domingos não é contabilizado farm de Alumínio. Os valores serão zerados ao final do dia para a nova semana."
    
    aba_nome, coluna = dias[hoje]  # Define qual aba e qual coluna usar
    
    try:
        # Tente acessar a planilha
        aba = sheet.worksheet(aba_nome)
    except (gspread.exceptions.APIError, gspread.exceptions.GSpreadException) as e:
        logger.warning(f"⚠️ Erro de conexão com Google Sheets: {str(e)}. Reconectando...")
        reconnect_sheets()
        
        # Tentar novamente após reconexão
        try:
            aba = sheet.worksheet(aba_nome)
        except Exception as e:
            logger.error(f"❌ Falha na reconexão: {str(e)}")
            save_pending_update(passaporte, quantidade, operacao)
            return f"⚠️ Problema temporário de conexão com a planilha. Seu registro ({passaporte}, {quantidade}x, {operacao}) foi salvo e será processado em breve."

    try:
        # Encapsular operações em função para retry
        def update_operation():
            # Buscar o passaporte na planilha
            cell = aba.find(str(passaporte))

            if cell:
                row = cell.row
                current_value = aba.cell(row, coluna).value
                current_value = int(current_value if current_value else 0)
                
                # Verificar se é para guardar ou retirar
                if operacao == "guardar":
                    novo_valor = current_value + quantidade
                    action_text = "adicionou"
                else:  # retirar
                    novo_valor = max(0, current_value - quantidade)  # Não permitir valor negativo
                    action_text = "retirou"
                
                # Atualização mais eficiente com cell_range
                cell_range = f"{gspread.utils.rowcol_to_a1(row, coluna)}"
                aba.update(cell_range, [[novo_valor]])
                return novo_valor, False, action_text
            else:
                # Para novos registros, só permitimos guardar (não faz sentido retirar algo que não existe)
                if operacao == "retirar":
                    return 0, True, "tentou retirar"
                    
                novo_valor = quantidade
                # Criar uma linha com espaços vazios até a coluna desejada
                new_row = [passaporte] + [""] * (coluna - 2) + [novo_valor]
                aba.append_row(new_row)
                return novo_valor, True, "adicionou"

        # Executar com retry
        novo_valor, is_new, action_text = update_with_exponential_backoff(update_operation)

        # Preparar mensagem de sucesso
        if is_new and operacao == "retirar":
            message = f"⚠️ **Passaporte {passaporte}** tentou retirar **{quantidade}x Alumínio**, mas não é da PASTELARIA DO CHINA."
            logger.info(f"⚠️ Tentativa de retirada sem registro: {passaporte} tentou retirar {quantidade} Alumínio em {aba_nome}, coluna {coluna}")
        else:
            action = "criado novo registro" if is_new else "atualizado registro existente"
            op_text = "registrou" if operacao == "guardar" else "retirou"
            message = f"✅ **Passaporte {passaporte}** {op_text} **{quantidade}x Alumínio** em `{aba_nome}` no báu de Membros da PASTELARIA. {action.capitalize()} Meta Semanal: {novo_valor}."
            if operacao == "guardar":
                message += " Contribuição adicionada à sua meta semanal!"
            logger.info(f"✅ {action}: {passaporte} {action_text} {quantidade} Alumínio em {aba_nome}, coluna {coluna}")
        
        return message
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar planilha: {str(e)}")
        save_pending_update(passaporte, quantidade, operacao)
        return f"⚠️ Problema ao atualizar a planilha. Seu registro ({passaporte}, {quantidade}x, {operacao}) foi salvo e será processado em breve."

# ======================== FUNÇÃO PARA RESET DOMINICAL ======================== #

def reset_domingo():
    try:
        logger.info("🔄 Iniciando reset dominical...")
        
        # Lista de abas que precisam ser resetadas
        abas_para_resetar = ["FARM SEG E TER", "FARM QUR E QUI", "FARM SEX E SÁB"]
        
        # Reset das colunas 5 e 14 em cada aba usando atualizações em lote
        for aba_nome in abas_para_resetar:
            try:
                aba = sheet.worksheet(aba_nome)
                
                # Obter todos os IDs (coluna 2)
                ids = aba.col_values(2)
                
                # Preparar atualizações em lote
                batch_updates = []
                
                # Pular a primeira linha (cabeçalho)
                for i, id_valor in enumerate(ids[1:], start=2):
                    if id_valor and id_valor.strip():  # Se tiver ID na linha
                        # Adicionar coluna 5 (E) para atualização
                        batch_updates.append({
                            'range': f'E{i}',
                            'values': [[0]]
                        })
                        
                        # Adicionar coluna 14 (N) para atualização
                        batch_updates.append({
                            'range': f'N{i}',
                            'values': [[0]]
                        })
                
                # Aplicar todas as atualizações de uma vez
                if batch_updates:
                    aba.batch_update(batch_updates)
                
                logger.info(f"✅ Zerados os valores da aba {aba_nome}")
            except Exception as e:
                logger.error(f"❌ Erro ao resetar aba {aba_nome}: {str(e)}")
        
        # Resetar coluna J (10) do painel de controle para -1000
        try:
            painel = sheet.worksheet(PAINEL_CONTROLE)
            
            # Obter todos os IDs (coluna 2)
            ids = painel.col_values(2)
            
            # Preparar atualizações em lote
            batch_updates = []
            
            # Para cada ID, resetar o valor na coluna J (10)
            for i, id_valor in enumerate(ids[1:], start=2):  # Começando da linha 2 (pulando cabeçalho)
                if id_valor and id_valor.strip():  # Se tiver ID na linha
                    batch_updates.append({
                        'range': f'J{i}',
                        'values': [[-1000]]
                    })
            
            # Aplicar todas as atualizações de uma vez
            if batch_updates:
                painel.batch_update(batch_updates)
            
            logger.info("✅ Resetada a coluna J do painel de controle para -1000")
        except Exception as e:
            logger.error(f"❌ Erro ao resetar painel de controle: {str(e)}")
        
        logger.info("✅ Reset dominical concluído com sucesso!")
        return True
    except Exception as e:
        logger.error(f"❌ Erro geral ao realizar reset dominical: {str(e)}")
        return False

# ======================== EVENTOS DO DISCORD ======================== #

# Configurar Intents do Discord
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
discord_client = discord.Client(intents=intents)

@discord_client.event
async def on_ready():
    logger.info(f'✅ Bot conectado como {discord_client.user}')
    
    # Tentar processar atualizações pendentes ao iniciar
    process_pending_updates()
    
    # Use o horário de Brasília para verificações de tempo
    brazil_now = get_brazil_datetime()
    hoje = brazil_now.weekday()
    hora_atual = brazil_now.hour
    
    # Log com horário de Brasília para debug
    logger.info(f"🕒 Horário de Brasília: {brazil_now.strftime('%Y-%m-%d %H:%M:%S')} (Dia: {hoje}, Hora: {hora_atual})")
    
    # Se for domingo, verifica se já é de noite para realizar o reset
    if hoje == 6 and hora_atual >= 12:  # Domingo e após 12h
        logger.info("🔄 Domingo à noite. Verificando se é necessário realizar o reset...")
        reset_domingo()

@discord_client.event
async def on_message(message):
    if message.author.bot:
        return  # Ignorar mensagens de outros bots


    logger.debug(f"📩 Mensagem recebida no canal {message.channel}: {message.content}")

    try:
        # Comandos especiais
        if message.content.lower().startswith("!reset") and message.author.guild_permissions.administrator:
            hoje = get_brazil_datetime().weekday()
            if hoje == 6:  # É domingo
                if reset_domingo():
                    await message.channel.send("✅ **Reset dominical realizado com sucesso!** Valores zerados e metas resetadas para -1000.")
                else:
                    await message.channel.send("❌ **Erro ao realizar reset dominical.** Verifique os logs para mais detalhes.")
            else:
                await message.channel.send("⚠️ O reset manual só pode ser realizado aos domingos.")
            return
        
        # Comando de ajuda
        if message.content.lower() in ["!ajuda", "!help"]:
            help_text = (
                "**📋 Comandos do Bot de Alumínio:**\n\n"
                "**Para registrar alumínio:**\n"
                "- `Passaporte: 123 Guardou: 50x Alumínio`\n"
                "- `Pass: 123 Guardou: 50x Al`\n\n"
                "**Para retirar alumínio:**\n"
                "- `Passaporte: 123 Retirou: 50x Alumínio`\n"
                "- `Pass: 123 Retirou: 50x Al`\n\n"
                "**Comandos administrativos:**\n"
                "- `!reset` - Reseta os valores (apenas admins, apenas domingos)\n"
                "- `!ajuda` ou `!help` - Mostra esta mensagem\n\n"
                "**Observações:**\n"
                "- Registros aos domingos não são contabilizados\n"
                "- Reset automático ocorre aos domingos após 22h"
            )
            await message.channel.send(help_text)
            return
        # comando de template
        if message.content.lower() == "!add":
            template = "**Copie e complete o template abaixo:**\n`Passaporte: (inserir) Guardou: (quantidade)x Alumínio`"
            await message.channel.send(template)
            return
        
        # Extrair passaporte, quantidade e operação da mensagem
        passaporte, quantidade, operacao = extract_data(message.content)

        # Se encontrou os dados de passaporte e quantidade, atualize a planilha
        if passaporte and quantidade > 0:
            resposta = update_sheet(passaporte, quantidade, operacao)
            
            # Enviar resposta com tratamento de rate limit
            try:
                await message.channel.send(resposta)
            except discord.errors.HTTPException as e:
                if e.status == 429:  # Rate limit
                    retry_after = e.retry_after
                    logger.warning(f"⏳ Rate limit atingido. Tentando novamente em {retry_after}s")
                    await asyncio.sleep(retry_after)
                    await message.channel.send(resposta)
                else:
                    logger.error(f"❌ Erro HTTP ao enviar mensagem: {str(e)}")
            except Exception as e:
                logger.error(f"❌ Erro ao enviar mensagem: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Erro ao processar mensagem: {str(e)}")
        try:
            await message.channel.send(f"❌ Ocorreu um erro ao processar esta mensagem: {str(e)}")
        except:
            pass

# ======================== GERENCIAMENTO DE ENCERRAMENTO GRACIOSO ======================== #

def signal_handler(sig, frame):
    logger.info("👋 Encerrando o bot...")
    asyncio.run(discord_client.close())
    logger.info("✅ Bot desconectado com sucesso.")
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ======================== FUNÇÕES DE VERIFICAÇÃO PERIÓDICA ======================== #

async def periodic_tasks():
    while True:
        try:
            # Verificar se é domingo e se já é hora de reset (12h)
            brazil_now = get_brazil_datetime()
            hoje = brazil_now.weekday()
            hora_atual = brazil_now.hour
            
            # Adicionar log com horário de Brasília para debug
            logger.debug(f"🕒 Verificação periódica usando horário de Brasília: {brazil_now.strftime('%Y-%m-%d %H:%M:%S')} (Dia: {hoje}, Hora: {hora_atual})")
            
            if hoje == 6 and hora_atual >= 12:  # Domingo após 12h
                logger.info("🔄 Verificação periódica: Domingo à noite. Verificando se é necessário realizar o reset...")
                reset_domingo()
            
            # Processar atualizações pendentes
            process_pending_updates()
            
            # Verificar saúde da conexão com o Google Sheets
            if sheet is None:
                logger.warning("⚠️ Conexão com Google Sheets perdida. Tentando reconectar...")
                reconnect_sheets()
            
        except Exception as e:
            logger.error(f"❌ Erro nas tarefas periódicas: {str(e)}")
        
        # Aguardar 30 minutos antes da próxima verificação
        await asyncio.sleep(1800)

# ======================== INICIAR O BOT E O FLASK EM PARALELO ======================== #

def run_discord_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Adicionar tarefa periódica ao loop do Discord
    loop.create_task(periodic_tasks())
    
    # Iniciar o bot Discord
    loop.run_until_complete(discord_client.start(DISCORD_TOKEN))

if __name__ == "__main__":
    # Iniciar o Flask em uma thread separada PRIMEIRO
    logger.info("🚀 Iniciando servidor Flask...")
    flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=8080))
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("✅ Servidor Flask iniciado na porta 8080")
    
    # Esperar um pouco para garantir que o Flask inicializou
    time.sleep(3)
    
    # Agora tentar conectar ao Google Sheets
    try:
        logger.info("🔄 Tentando conectar ao Google Sheets...")
        connect_to_sheets()
        logger.info("✅ Conexão com Google Sheets estabelecida com sucesso!")
    except Exception as e:
        logger.error(f"❌ Erro ao conectar com Google Sheets: {str(e)}")
        logger.info("⚠️ O bot continuará tentando reconectar periodicamente")
    
    # Rodar o bot do Discord em uma thread separada
    logger.info("🔄 Iniciando bot Discord...")
    discord_thread = Thread(target=run_discord_bot)
    discord_thread.daemon = True
    discord_thread.start()
    
    # Manter a thread principal viva
    try:
        while True:
            # Tentar reconectar se a conexão estiver perdida
            if sheet is None:
                logger.info("🔄 Tentando reconectar ao Google Sheets...")
                try:
                    reconnect_sheets()
                except Exception as e:
                    logger.error(f"❌ Erro na reconexão: {str(e)}")
            
            time.sleep(3600)  # Verifica a cada hora
    except KeyboardInterrupt:
        logger.info("👋 Programa interrompido manualmente.")