#!/usr/bin/env python3
import time
import urllib.request
import json
import os
import sys

def main():
    print("====================================================")
    print("   Telegram Chat-ID Finder für Andacht-Sender")
    print("====================================================\n")
    
    # Check if .env already exists and contains token
    token = ""
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass

    if token:
        use_existing = input(f"Bestehenden Bot-Token aus .env verwenden ({token[:10]}...)? [J/n]: ").strip().lower()
        if use_existing in ('n', 'no', 'nein'):
            token = ""

    if not token:
        token = input("Bitte gib deinen Telegram Bot Token ein: ").strip()
        if not token:
            print("Fehler: Kein Token eingegeben.")
            sys.exit(1)

    print("\nVerbindung zum Bot wird überprüft...")
    # Get bot info to verify token
    info_url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(info_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if res_data.get("ok"):
                bot_name = res_data["result"].get("first_name", "Bot")
                bot_username = res_data["result"].get("username", "bot")
                print(f"Erfolg! Verbunden mit Bot: @{bot_username} ({bot_name})")
            else:
                print("Fehler: Token ist ungültig oder der Bot wurde nicht gefunden.")
                sys.exit(1)
    except Exception as e:
        print(f"Fehler bei der Verbindung mit Telegram: {e}")
        print("Bitte überprüfe deinen Token und deine Internetverbindung.")
        sys.exit(1)

    print("\n----------------------------------------------------")
    print(f"Schritt: Sende jetzt eine Nachricht (z. B. 'Hallo') an den Bot @{bot_username}.")
    print("Das Skript wartet nun auf deine Nachricht, um deine Chat-ID zu ermitteln...")
    print("----------------------------------------------------\n")

    updates_url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    # Get current updates offset to ignore older messages
    offset = 0
    try:
        req = urllib.request.Request(updates_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if res_data.get("ok") and res_data.get("result"):
                offset = res_data["result"][-1]["update_id"] + 1
    except Exception:
        pass

    try:
        while True:
            url = f"{updates_url}?offset={offset}&timeout=5"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
            except Exception as e:
                # Timeout or network glitch, retry
                time.sleep(2)
                continue

            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    # Update offset to ignore this update next time
                    offset = update["update_id"] + 1
                    
                    if "message" in update:
                        chat = update["message"]["chat"]
                        chat_id = chat["id"]
                        first_name = chat.get("first_name", "Benutzer")
                        text = update["message"].get("text", "")
                        
                        print(f"Empfangene Nachricht: '{text}' von {first_name}!")
                        print(f"Erkannte Chat-ID: {chat_id}")
                        
                        # Write or update .env file
                        env_lines = []
                        voice_defined = False
                        if os.path.exists(".env"):
                            with open(".env", "r", encoding="utf-8") as f:
                                for line in f:
                                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                                        continue
                                    if line.startswith("TELEGRAM_CHAT_ID="):
                                        continue
                                    if line.startswith("TTS_VOICE="):
                                        voice_defined = True
                                    env_lines.append(line)
                        
                        # Add new values at the start
                        new_env = [
                            f"TELEGRAM_BOT_TOKEN={token}\n",
                            f"TELEGRAM_CHAT_ID={chat_id}\n"
                        ]
                        
                        if not voice_defined:
                            new_env.append("TTS_VOICE=de-DE-ConradNeural\n")
                            
                        # Add remaining lines, clean up extra newlines at the end
                        new_env.extend(env_lines)
                        
                        with open(".env", "w", encoding="utf-8") as f:
                            f.writelines(new_env)
                            
                        print("\n====================================================")
                        print("Erfolg! Die Datei .env wurde erfolgreich erstellt!")
                        print(f"Bot-Token und Chat-ID ({chat_id}) sind gespeichert.")
                        print("====================================================")
                        return
                        
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nAbgebrochen durch Benutzer.")
        sys.exit(0)

if __name__ == "__main__":
    main()
