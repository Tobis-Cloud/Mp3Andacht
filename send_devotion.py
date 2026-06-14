#!/usr/bin/env python3
import os
import sys
import argparse
import datetime
import asyncio
import json
import urllib.request
import uuid
import re
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

def get_devotion(day: int, month_name: str, md_path: str):
    """
    Parses the markdown file and extracts the devotion text for the given date.
    """
    if not os.path.exists(md_path):
        print(f"Fehler: Andachtsdatei nicht gefunden unter {md_path}")
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
        # Stop at the next main header
        if stripped.startswith("# "):
            break
        devotion_lines.append(line)

    return "".join(devotion_lines).strip()

def clean_text_for_audio(text: str) -> str:
    """
    Cleans devotion text for audio output:
    - Normalizes line breaks.
    - Joins single newlines within paragraphs with spaces to avoid stuttering/unnatural pauses.
    - Keeps double newlines as paragraph boundaries.
    """
    text = text.replace('\r\n', '\n')
    paragraphs = text.split('\n\n')
    cleaned_paragraphs = []
    for para in paragraphs:
        lines = [line.strip() for line in para.split('\n') if line.strip()]
        cleaned_para = " ".join(lines)
        if cleaned_para:
            cleaned_paragraphs.append(cleaned_para)
    return "\n\n".join(cleaned_paragraphs)

async def generate_audio(text: str, output_path: str, voice: str):
    """
    Generates an MP3 file from text using edge-tts.
    """
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def send_telegram_audio(token: str, chat_id: str, filepath: str, caption: str):
    """
    Sends an audio file to Telegram using multipart/form-data.
    """
    boundary = uuid.uuid4().hex
    filename = os.path.basename(filepath)
    
    with open(filepath, 'rb') as f:
        file_data = f.read()

    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'User-Agent': 'Mozilla/5.0'
    }

    parts = []
    # Chat ID
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode('utf-8'))
    # Caption
    if caption:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode('utf-8'))
    # Audio
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{filename}"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode('utf-8'))
    parts.append(file_data)
    parts.append(f'\r\n--{boundary}--\r\n'.encode('utf-8'))

    body = b''.join(parts)
    url = f"https://api.telegram.org/bot{token}/sendAudio"
    
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def send_telegram_message(token: str, chat_id: str, text: str):
    """
    Sends a text message to Telegram, with markdown formatting support and fallback to plain text.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }
    
    # Telegram limit is 4096. We split it safely just in case.
    max_len = 4000
    messages = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    
    for msg in messages:
        # Try with Markdown formatting first
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
            # Fallback to plain text if Markdown fails (e.g. unclosed asterisks/quotes)
            data_plain = json.dumps({
                "chat_id": chat_id,
                "text": msg
            }).encode('utf-8')
            req_plain = urllib.request.Request(url, data=data_plain, headers=headers, method='POST')
            with urllib.request.urlopen(req_plain) as response:
                pass

def main():
    parser = argparse.ArgumentParser(description="Täglichen Andacht-Sender")
    parser.add_argument("--date", help="Datum im Format 'Tag. Monat' (z.B. '13. Juni')")
    parser.add_argument("--test", action="store_true", help="Sendet eine kurze Test-Nachricht")
    args = parser.parse_args()

    # Load configuration
    script_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(script_dir, ".env"))

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    voice = os.getenv("TTS_VOICE", "de-DE-ConradNeural")

    if not bot_token or not chat_id:
        print("Fehler: TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID nicht in .env konfiguriert.")
        print("Bitte führe zuerst 'python get_chat_id.py' aus, um die Konfiguration zu erstellen.")
        sys.exit(1)

    if args.test:
        print("Sende Testnachricht...")
        test_text = "Hallo! Dies ist ein Funktionstest des Andacht-Senders. Die Audio-Generierung und der Telegram-Versand funktionieren einwandfrei."
        test_mp3 = os.path.join(script_dir, "test_andacht.mp3")
        try:
            asyncio.run(generate_audio(test_text, test_mp3, voice))
            send_telegram_audio(bot_token, chat_id, test_mp3, "Test-Andacht Sprachprobe")
            send_telegram_message(bot_token, chat_id, "*Test-Andacht*\n\nDie Verbindung wurde erfolgreich getestet!")
            print("Erfolg! Test-Audio und Nachricht gesendet.")
        except Exception as e:
            print(f"Fehler beim Testlauf: {e}")
        finally:
            if os.path.exists(test_mp3):
                os.remove(test_mp3)
        return

    # Determine date
    if args.date:
        match = re.match(r"(\d+)\.\s*(\w+)", args.date)
        if not match:
            print("Fehler: Falsches Datumsformat. Erwartet wird z.B. '13. Juni' oder '1. Januar'.")
            sys.exit(1)
        day = int(match.group(1))
        month_name = match.group(2)
    else:
        # Use German timezone to ensure correct date even on cloud servers
        try:
            from zoneinfo import ZoneInfo
            now = datetime.datetime.now(ZoneInfo("Europe/Berlin"))
        except ImportError:
            now = datetime.datetime.now()
        day = now.day
        month_name = GERMAN_MONTHS[now.month]

    print(f"Verarbeite Andacht für den {day}. {month_name}...")

    # Parse devotion
    md_path = os.path.join(script_dir, "Auf_dein_Wort_digitalisiert.md")
    devotion_text = get_devotion(day, month_name, md_path)

    if not devotion_text:
        print(f"Fehler: Keine Andacht für den {day}. {month_name} gefunden.")
        sys.exit(1)

    print("Andachtstext erfolgreich geladen. Generiere Audio...")

    # Format text for reading (clean up newlines for fluent reading)
    cleaned_devotion = clean_text_for_audio(devotion_text)
    audio_text = f"Andacht für den {day}. {month_name}.\n\n{cleaned_devotion}"
    
    # Generate MP3
    briefing_dir = os.path.join(script_dir, "briefing")
    os.makedirs(briefing_dir, exist_ok=True)
    mp3_filename = f"andacht_{day}_{month_name.lower()}.mp3"
    mp3_path = os.path.join(briefing_dir, mp3_filename)

    # Load subscribers
    subscribers_path = os.path.join(script_dir, "subscribers.json")
    chat_ids = set()
    if chat_id:
        chat_ids.add(str(chat_id))
    
    if os.path.exists(subscribers_path):
        try:
            with open(subscribers_path, 'r', encoding='utf-8') as f:
                subs = json.load(f)
                if isinstance(subs, list):
                    for cid in subs:
                        chat_ids.add(str(cid))
        except Exception as e:
            print(f"Warnung: Abonnenten konnten nicht geladen werden: {e}")

    try:
        asyncio.run(generate_audio(audio_text, mp3_path, voice))
        print(f"Audio erfolgreich generiert. Sende an {len(chat_ids)} Empfänger...")

        # Format text for Telegram message (Premium look)
        telegram_message = f"*Auf dein Wort — Andacht vom {day}. {month_name}*\n\n{devotion_text}"

        # Send Audio & Message to all subscribers
        for cid in chat_ids:
            try:
                send_telegram_audio(bot_token, cid, mp3_path, f"Andacht {day}. {month_name}")
                send_telegram_message(bot_token, cid, telegram_message)
                print(f"Erfolgreich an Chat-ID {cid} gesendet.")
            except Exception as se:
                print(f"Fehler beim Senden an Chat-ID {cid}: {se}")

    except Exception as e:
        print(f"Fehler während der Verarbeitung/Versand: {e}")
        sys.exit(1)
    finally:
        # Keep the MP3 file in the briefing directory for GitHub commit
        pass

if __name__ == "__main__":
    main()
