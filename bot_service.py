#!/usr/bin/env python3
import os
import sys
import time
import asyncio
import json
import urllib.request
import urllib.parse
import urllib.error
import socket
import uuid
import re
import datetime
from dotenv import load_dotenv

# German months mapping
GERMAN_MONTHS = {
    1: "Januar",
    2: "Februar",
    3: "März",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember"
}

# Load configuration
script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(script_dir, ".env"))

bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
subscribers_file = os.path.join(script_dir, "subscribers.json")
md_path = os.path.join(script_dir, "Auf_dein_Wort_digitalisiert.md")

if not bot_token:
    print("Fehler: TELEGRAM_BOT_TOKEN nicht in .env konfiguriert.")
    sys.exit(1)

def get_voice():
    # Reload dotenv to get fresh voice setting if edited
    load_dotenv(os.path.join(script_dir, ".env"), override=True)
    return os.getenv("TTS_VOICE", "de-DE-KillianNeural")

def clean_text_for_audio(text: str) -> str:
    text = text.replace('\r\n', '\n')
    paragraphs = text.split('\n\n')
    cleaned_paragraphs = []
    for para in paragraphs:
        lines = [line.strip() for line in para.split('\n') if line.strip()]
        cleaned_para = " ".join(lines)
        if cleaned_para:
            cleaned_paragraphs.append(cleaned_para)
    return "\n\n".join(cleaned_paragraphs)

def get_devotion(day: int, month_name: str):
    if not os.path.exists(md_path):
        return None

    target_header = f"# {day}. {month_name}"
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == target_header:
            start_idx = idx + 1
            break

    if start_idx is None:
        return None

    devotion_lines = []
    for line in lines[start_idx:]:
        stripped = line.strip()
        if stripped.startswith("# "):
            break
        devotion_lines.append(line)

    return "".join(devotion_lines).strip()

async def generate_audio(text: str, output_path: str, voice: str):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def send_telegram_audio(token: str, chat_id: str, filepath: str, caption: str):
    boundary = uuid.uuid4().hex
    filename = os.path.basename(filepath)
    with open(filepath, 'rb') as f:
        file_data = f.read()

    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'User-Agent': 'Mozilla/5.0'
    }

    parts = []
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode('utf-8'))
    if caption:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode('utf-8'))
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{filename}"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode('utf-8'))
    parts.append(file_data)
    parts.append(f'\r\n--{boundary}--\r\n'.encode('utf-8'))

    body = b''.join(parts)
    url = f"https://api.telegram.org/bot{token}/sendAudio"
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }
    
    max_len = 4000
    messages = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    
    for msg in messages:
        data = json.dumps({
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown"
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req) as response:
                pass
        except Exception:
            data_plain = json.dumps({
                "chat_id": chat_id,
                "text": msg
            }).encode('utf-8')
            req_plain = urllib.request.Request(url, data=data_plain, headers=headers, method='POST')
            with urllib.request.urlopen(req_plain) as response:
                pass

def add_subscriber(chat_id):
    chat_id = str(chat_id)
    subscribers = []
    if os.path.exists(subscribers_file):
        try:
            with open(subscribers_file, 'r', encoding='utf-8') as f:
                subscribers = json.load(f)
        except Exception:
            pass
    
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        with open(subscribers_file, 'w', encoding='utf-8') as f:
            json.dump(subscribers, f, indent=2)
        return True
    return False

def remove_subscriber(chat_id):
    chat_id = str(chat_id)
    subscribers = []
    if os.path.exists(subscribers_file):
        try:
            with open(subscribers_file, 'r', encoding='utf-8') as f:
                subscribers = json.load(f)
        except Exception:
            pass
            
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        with open(subscribers_file, 'w', encoding='utf-8') as f:
            json.dump(subscribers, f, indent=2)
        return True
    return False

async def handle_devotion_request(chat_id, day, month_name):
    # Send status
    send_telegram_message(bot_token, chat_id, f"⏳ Generiere Andacht für den *{day}. {month_name}*...")
    
    devotion_text = get_devotion(day, month_name)
    if not devotion_text:
        send_telegram_message(bot_token, chat_id, f"❌ Keine Andacht für den {day}. {month_name} gefunden.")
        return

    # Clean text and construct audio text
    cleaned = clean_text_for_audio(devotion_text)
    audio_text = f"Andacht für den {day}. {month_name}.\n\n{cleaned}"
    
    mp3_filename = f"andacht_req_{chat_id}_{day}_{month_name.lower()}.mp3"
    mp3_path = os.path.join(script_dir, mp3_filename)
    
    voice = get_voice()
    
    try:
        await generate_audio(audio_text, mp3_path, voice)
        # Send audio
        send_telegram_audio(bot_token, chat_id, mp3_path, f"Andacht {day}. {month_name}")
        # Send text
        telegram_message = f"*Auf dein Wort — Andacht vom {day}. {month_name}*\n\n{devotion_text}"
        send_telegram_message(bot_token, chat_id, telegram_message)
    except Exception as e:
        print(f"Fehler bei Anfrage-Verarbeitung: {e}")
        send_telegram_message(bot_token, chat_id, f"❌ Fehler bei der Generierung: {e}")
    finally:
        if os.path.exists(mp3_path):
            os.remove(mp3_path)

def process_message(msg):
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = msg.get("text", "").strip()
    
    if not chat_id or not text:
        return

    # /start or /help
    if text.startswith("/start") or text.startswith("/hilfe") or text.startswith("/help"):
        help_text = (
            "✨ *Willkommen beim Andachts-Bot!* ✨\n\n"
            "Ich lese dir die Andachten aus *'Auf dein Wort'* vor.\n\n"
            "📖 *Befehle:*\n"
            "• `/heute` - Heutige Andacht abrufen (Audio & Text)\n"
            "• `/datum [Tag. Monat]` - Andacht für ein bestimmtes Datum abrufen (z.B. `/datum 24. Dezember`)\n"
            "• `/abo` - Die täglichen Andachten abonnieren (jeden Morgen um 07:00 Uhr)\n"
            "• `/stop` - Das tägliche Abonnement kündigen\n\n"
            "💡 Du kannst mir auch einfach ein Datum direkt schicken (z.B. `13. Juni` oder `1. Januar`)."
        )
        send_telegram_message(bot_token, chat_id, help_text)
        return

    # /abo /subscribe
    if text.startswith("/abo") or text.startswith("/subscribe"):
        if add_subscriber(chat_id):
            send_telegram_message(bot_token, chat_id, "✅ *Abonnement erfolgreich!* Du erhältst die Andachten ab jetzt jeden Morgen um 07:00 Uhr.")
        else:
            send_telegram_message(bot_token, chat_id, "ℹ️ Du hast die täglichen Andachten bereits abonniert.")
        return

    # /stop /unsubscribe
    if text.startswith("/stop") or text.startswith("/unsubscribe"):
        if remove_subscriber(chat_id):
            send_telegram_message(bot_token, chat_id, "🛑 *Abonnement beendet.* Du erhältst ab jetzt keine täglichen Nachrichten mehr.")
        else:
            send_telegram_message(bot_token, chat_id, "ℹ️ Du hattest kein aktives Abonnement.")
        return

    # /heute /today
    if text.startswith("/heute") or text.startswith("/today"):
        now = datetime.datetime.now()
        day = now.day
        month_name = GERMAN_MONTHS[now.month]
        asyncio.run(handle_devotion_request(chat_id, day, month_name))
        return

    # /datum or general date query
    date_query = text
    if text.startswith("/datum"):
        date_query = text.replace("/datum", "", 1).strip()
        
    match = re.match(r"(\d+)\.\s*(\w+)", date_query)
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        # Check if month name is valid in German
        if month_name in GERMAN_MONTHS.values():
            asyncio.run(handle_devotion_request(chat_id, day, month_name))
            return

    # If nothing matched, send instructions
    send_telegram_message(
        bot_token, 
        chat_id, 
        "❓ *Befehl nicht verstanden.*\nSchreibe `/heute`, `/abo` oder ein Datum wie `24. Dezember`."
    )

def main():
    print("Interaktiver Telegram-Bot-Dienst gestartet...")
    offset = 0
    updates_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"

    # Long polling loop
    while True:
        try:
            url = f"{updates_url}?offset={offset}&timeout=30"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            try:
                with urllib.request.urlopen(req, timeout=35) as response:
                    data = json.loads(response.read().decode('utf-8'))
            except (socket.timeout, urllib.error.URLError) as e:
                # Handle timeouts and typical transient connection errors silently
                # to avoid filling logs during standard long-polling operations.
                if isinstance(e, urllib.error.URLError) and not isinstance(e.reason, socket.timeout):
                    # If it's a real URL error (e.g. no internet connection at startup)
                    print(f"Verbindungsfehler (wird in 5s wiederholt): {e}")
                    time.sleep(5)
                continue
                
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        process_message(update["message"])
                        
        except KeyboardInterrupt:
            print("Bot-Dienst beendet.")
            break
        except Exception as e:
            print(f"Fehler in der Polling-Schleife: {e}")
            time.sleep(5)  # Wait on error to avoid spamming the API

if __name__ == "__main__":
    main()
