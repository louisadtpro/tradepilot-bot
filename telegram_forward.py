import asyncio
import os
from telethon import TelegramClient, events

# ─── CONFIG ──────────────────────────────────────────────
API_ID    = 36503830
API_HASH  = '0381f472b39c7dd3215e032fafc300d7'
SESSION   = 'tradepilot_forward'

# Channel source (où tu reçois les signaux)
SOURCE_ID = -1004389587969

# Channel destination (ton Signal VIP clients)
DEST_ID   = -1003951755108

# ─── SCRIPT ──────────────────────────────────────────────
client = TelegramClient(SESSION, API_ID, API_HASH)

@client.on(events.NewMessage(chats=SOURCE_ID))
async def forward_signal(event):
    msg = event.message
    print(f"📡 Signal reçu : {msg.text[:50]}...")
    
    try:
        if msg.media:
            # Message avec media (image, video, document...)
            await client.send_file(DEST_ID, msg.media, caption=msg.text or "")
            print(f"✅ Media + texte copie vers le channel VIP")
        elif msg.text:
            # Message texte uniquement
            await client.send_message(DEST_ID, msg.text)
            print(f"✅ Signal texte copie vers le channel VIP")
    except Exception as e:
        print(f"❌ Erreur copie : {e}")

async def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  ⚡ TradePilot Signal Forwarder")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    await client.start()
    
    # Verifier les channels
    try:
        source = await client.get_entity(SOURCE_ID)
        print(f"✅ Channel source : {source.title}")
    except Exception as e:
        print(f"❌ Channel source introuvable : {e}")
        return
    
    try:
        dest = await client.get_entity(DEST_ID)
        print(f"✅ Channel destination : {dest.title}")
    except Exception as e:
        print(f"❌ Channel destination introuvable : {e}")
        return
    
    print(f"\n📡 En attente de signaux...")
    print(f"Source  → {source.title}")
    print(f"Dest    → {dest.title}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
