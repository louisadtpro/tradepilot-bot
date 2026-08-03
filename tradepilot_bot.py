import os
import time
import asyncio
import secrets
import discord
from discord.ext import commands
from discord.ui import Button, View
from flask import Flask, request, jsonify, redirect, session, render_template_string
from functools import wraps
import requests as http_requests
import threading

# ════════════════════════════════════════════════════════
#  CONFIG — IDs
# ════════════════════════════════════════════════════════
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "COLLE_TON_TOKEN_ICI")

GUILD_ID       = 1518723776823558184
VENTES_CH      = 1519256169338638346   # #ventes-dashboard
ARRIVANTS_CH   = 1522177979709526056   # salon bienvenue
LOGS_CH        = 1522505084318122155   # logs tickets

# Salons boutons (par ID)
CH_TICKET      = 1519364425746874459   # ouvrir-un-ticket
CH_LIC         = 1519041523528892536   # support-licence
CH_SETUP       = 1519364321300320326   # support-setup
CH_VIP         = 1519363058076487821   # support-vip

# Rôles
ROLE_MEMBRE    = 1518986286273134843
ROLE_ADMIN     = 1518731166277046372
ROLES = {
    "licence" : 1519020532555583610,
    "setup"   : 1519019672131993790,
    "signal"  : 1519018716459696209,
}

PRODUCT_LABELS = {
    "licence" : "🔑 Licence — 99€",
    "setup"   : "⚙️ Setup Pro — 200€",
    "signal"  : "📡 Signal VIP — 59.99€/mois",
}

TICKET_MESSAGES = {
    "general": (
        "**Bonjour ! 👋**\n\n"
        "Un membre de l'équipe TradePilot va te répondre dans les plus brefs délais.\n\n"
        "**Explique-nous :**\n"
        "→ Ta question ou ton problème ?\n\n"
        "Nous répondons dans la journée ✅"
    ),
    "licence": (
        "**Bonjour ! 👋**\n\n"
        "Tu as ouvert un ticket **Support Licence**.\n\n"
        "**Dis-nous :**\n"
        "→ Où en es-tu dans l'installation ?\n"
        "→ Quel message d'erreur tu vois ?\n\n"
        "On te répond dans la journée ✅"
    ),
    "setup": (
        "**Bonjour ! 👋**\n\n"
        "Tu as ouvert un ticket **Support Setup Pro**.\n\n"
        "**Prépare :**\n"
        "→ Ton broker (XM, IC Markets...)\n"
        "→ MT4 ou MT5 ?\n"
        "→ Installe TeamViewer ou AnyDesk\n\n"
        "On te contacte rapidement ✅"
    ),
    "vip": (
        "**Bonjour ! 👋**\n\n"
        "Tu as ouvert un ticket **Support Signal VIP**.\n\n"
        "**Dis-nous :**\n"
        "→ Tu ne reçois pas les signaux ?\n"
        "→ Tu as une question sur un signal ?\n\n"
        "On te répond dans la journée ✅"
    ),
    "achat": {
        "licence": (
            "**Bienvenue sur TradePilot ! 🎉**\n\n"
            "Tu viens d'acheter la **Licence** !\n\n"
            "**1️⃣** Envoie ta **confirmation Stripe** ici\n"
            "**2️⃣** Je t'envoie tes fichiers (EA + script)\n"
            "**3️⃣** Suis le guide dans **#guide-et-fichiers**\n\n"
            "Je réponds dans la journée ✅"
        ),
        "setup": (
            "**Bienvenue sur TradePilot ! 🎉**\n\n"
            "Tu viens d'acheter le **Setup Pro** !\n\n"
            "**1️⃣** Envoie ta **confirmation Stripe** ici\n"
            "**2️⃣** Dis-moi ton broker + MT4 ou MT5\n"
            "**3️⃣** Prépare TeamViewer ou AnyDesk\n\n"
            "Je réponds dans la journée ✅"
        ),
        "signal": (
            "**Bienvenue sur TradePilot ! 🎉**\n\n"
            "Tu viens de t'abonner au **Signal VIP** !\n\n"
            "**1️⃣** Envoie ta **confirmation Stripe** ici\n"
            "**2️⃣** Tes accès **#signaux-live** sont actifs\n"
            "**3️⃣** Lis **#guide-signal** pour comprendre\n\n"
            "⚠️ Signaux informatifs — tu restes responsable.\n"
            "Des questions ? Écris ici ✅"
        ),
    }
}

# ════════════════════════════════════════════════════════
#  HELPER : créer un ticket
# ════════════════════════════════════════════════════════
async def create_ticket(guild, member, ticket_type, label, msg_text, product_label=None):
    # Vérifie si un ticket existe déjà
    existing = discord.utils.get(
        guild.text_channels,
        name=f"ticket-{member.display_name.lower().replace(' ', '-')}"
    )
    if existing:
        return existing, True  # existe déjà

    category = discord.utils.get(guild.categories, name="🎫 TICKETS")
    if not category:
        category = await guild.create_category(
            "🎫 TICKETS",
            overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        )

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    ticket = await category.create_text_channel(
        f"ticket-{member.display_name.lower().replace(' ', '-')}",
        overwrites=overwrites,
        topic=f"{label} — {member.display_name}"
    )

    embed = discord.Embed(
        title=f"🎫 {label}",
        description=msg_text,
        color=0xF5B830
    )
    if product_label:
        embed.add_field(name="Produit", value=product_label, inline=True)
    embed.set_footer(text="TradePilot — Automatisation MT4 & MT5")
    await ticket.send(content=member.mention, embed=embed, view=CloseTicketView())

    return ticket, False


# ════════════════════════════════════════════════════════
#  VIEWS
# ════════════════════════════════════════════════════════
class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="tp_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("🔒 Sauvegarde en cours... fermeture dans 5 secondes.")

        # Sauvegarder les logs
        logs_ch = interaction.guild.get_channel(LOGS_CH)
        if logs_ch:
            messages = []
            async for msg in interaction.channel.history(limit=100, oldest_first=True):
                if msg.author.bot and not msg.content:
                    continue
                ts = msg.created_at.strftime("%d/%m %H:%M")
                if msg.content:
                    messages.append(f"[{ts}] {msg.author.display_name}: {msg.content}")
                elif msg.embeds and msg.embeds[0].title:
                    messages.append(f"[{ts}] {msg.author.display_name}: [Embed] {msg.embeds[0].title}")

            log_text = "\n".join(messages) if messages else "Aucun message."
            embed_log = discord.Embed(
                title=f"📋 Logs — {interaction.channel.name}",
                description=f"```{log_text[:3900]}```",
                color=0x95A5A6
            )
            embed_log.add_field(name="Fermé par", value=interaction.user.mention, inline=True)
            embed_log.add_field(name="Date", value=f"<t:{int(time.time())}:F>", inline=True)
            embed_log.set_footer(text="TradePilot — Logs Tickets")
            await logs_ch.send(embed=embed_log)

        await asyncio.sleep(5)
        await interaction.channel.delete()


class TicketView(View):
    def __init__(self, ticket_type, label):
        super().__init__(timeout=None)
        self.ticket_type = ticket_type
        self.label = label

    @discord.ui.button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="tp_ticket_general")
    async def open_general(self, interaction: discord.Interaction, button: Button):
        await handle_ticket_button(interaction, "general", "❓ Support TradePilot")

class SupportLicView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="tp_ticket_licence")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await handle_ticket_button(interaction, "licence", "🔑 Support Licence")

class SupportSetupView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="tp_ticket_setup")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await handle_ticket_button(interaction, "setup", "⚙️ Support Setup Pro")

class SupportVipView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="tp_ticket_vip")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await handle_ticket_button(interaction, "vip", "💎 Support Signal VIP")


async def handle_ticket_button(interaction: discord.Interaction, ticket_type: str, label: str):
    guild  = interaction.guild
    member = interaction.user

    ticket, already_exists = await create_ticket(
        guild, member, ticket_type, label,
        TICKET_MESSAGES.get(ticket_type, TICKET_MESSAGES["general"])
    )

    if already_exists:
        await interaction.response.send_message(
            f"Tu as déjà un ticket ouvert : {ticket.mention}", ephemeral=True
        )
        return

    # Notif admin
    ventes = guild.get_channel(VENTES_CH)
    if ventes:
        embed_v = discord.Embed(title="🎫 NOUVEAU TICKET SUPPORT", color=0xF5B830)
        embed_v.add_field(name="Client", value=f"{member.mention} ({member.display_name})", inline=True)
        embed_v.add_field(name="Type",   value=label,                                        inline=True)
        embed_v.add_field(name="Ticket", value=ticket.mention,                               inline=True)
        await ventes.send(content=f"<@&{ROLE_ADMIN}>", embed=embed_v)

    await interaction.response.send_message(
        f"✅ Ton ticket a été créé : {ticket.mention}", ephemeral=True
    )


# ════════════════════════════════════════════════════════
#  BOT
# ════════════════════════════════════════════════════════
intents = discord.Intents.all()

class TradePilotBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(CloseTicketView())
        self.add_view(TicketView("general", "Support"))
        self.add_view(SupportLicView())
        self.add_view(SupportSetupView())
        self.add_view(SupportVipView())
        print("✅ Views enregistrées")

bot = TradePilotBot()
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', secrets.token_hex(32))


# ════════════════════════════════════════════════════════
#  FLASK
# ════════════════════════════════════════════════════════
# ─── CONFIG DISCORD OAUTH ────────────────────────────────
DISCORD_CLIENT_ID     = os.environ.get('DISCORD_CLIENT_ID', 'COLLE_TON_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET', 'COLLE_TON_CLIENT_SECRET')
DISCORD_REDIRECT_URI  = os.environ.get('DISCORD_REDIRECT_URI', 'https://tradepilot-bot-production.up.railway.app/auth/callback')
DISCORD_API           = 'https://discord.com/api/v10'
GUILD_ID              = '1518723776823558184'

ROLES = {
    'licence': '1519020532555583610',
    'setup':   '1519019672131993790',
    'signal':  '1519018716459696209',
}

OAUTH_SCOPES = 'identify guilds.members.read'

# ─── HELPER ──────────────────────────────────────────────
def get_user_roles(access_token):
    """Recupere les roles du membre dans le serveur TradePilot"""
    headers = {'Authorization': f'Bearer {access_token}'}
    # Infos utilisateur
    user_r = http_requests.get(f'{DISCORD_API}/users/@me', headers=headers)
    if user_r.status_code != 200:
        return None, []
    user = user_r.json()
    # Roles dans le serveur
    member_r = http_requests.get(
        f'{DISCORD_API}/users/@me/guilds/{GUILD_ID}/member',
        headers=headers
    )
    if member_r.status_code != 200:
        return user, []
    member = member_r.json()
    return user, member.get('roles', [])

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/guide/login')
        return f(*args, **kwargs)
    return decorated

# ─── TEMPLATES ───────────────────────────────────────────
LOGIN_PAGE = '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TradePilot — Accès Guides</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#080B10;color:#E2E8F0;font-family:'Inter',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;}
  .box{background:#0D1117;border:1px solid #1E293B;border-radius:16px;padding:48px 40px;text-align:center;max-width:400px;width:90%;}
  .logo{font-size:24px;font-weight:900;color:#F5B830;letter-spacing:3px;margin-bottom:6px;}
  .subtitle{font-size:12px;color:#475569;letter-spacing:2px;text-transform:uppercase;margin-bottom:32px;}
  h1{font-size:22px;font-weight:700;color:#fff;margin-bottom:10px;}
  p{font-size:14px;color:#64748B;line-height:1.6;margin-bottom:32px;}
  .btn{display:inline-flex;align-items:center;gap:10px;background:#5865F2;color:#fff;padding:14px 28px;border-radius:10px;font-weight:700;font-size:15px;text-decoration:none;transition:opacity .2s;}
  .btn:hover{opacity:.9;}
  .btn svg{width:22px;height:22px;fill:white;}
  .info{margin-top:24px;font-size:12px;color:#334155;}
</style>
</head>
<body>
<div class="box">
  <div class="logo">TRADEPILOT</div>
  <div class="subtitle">Espace Clients</div>
  <h1>Accede a tes guides</h1>
  <p>Connecte-toi avec ton compte Discord pour acceder aux guides correspondant a ton offre.</p>
  <a href="/auth/discord" class="btn">
    <svg viewBox="0 0 71 55" xmlns="http://www.w3.org/2000/svg"><path d="M60.1 4.9A58.6 58.6 0 0 0 45.4.8a40.7 40.7 0 0 0-1.8 3.7 54.2 54.2 0 0 0-16.3 0A40.6 40.6 0 0 0 25.5.8 58.5 58.5 0 0 0 10.8 4.9C1.6 18.7-1 32.2.3 45.5a59.1 59.1 0 0 0 18 9.1 43.7 43.7 0 0 0 3.8-6.2 38.4 38.4 0 0 1-6-2.9l1.5-1.1a42.2 42.2 0 0 0 36 0l1.5 1.1a38.4 38.4 0 0 1-6 2.9 43.7 43.7 0 0 0 3.8 6.2 58.9 58.9 0 0 0 18.1-9.1C72.3 30 68.8 16.6 60.1 4.9ZM23.7 37.3c-3.5 0-6.4-3.2-6.4-7.1s2.8-7.1 6.4-7.1 6.5 3.2 6.4 7.1c0 3.9-2.8 7.1-6.4 7.1Zm23.6 0c-3.5 0-6.4-3.2-6.4-7.1s2.8-7.1 6.4-7.1 6.4 3.2 6.4 7.1-2.8 7.1-6.4 7.1Z"/></svg>
    Se connecter avec Discord
  </a>
  <div class="info">Seuls les membres avec un acces actif peuvent se connecter.</div>
</div>
</body>
</html>'''

ACCESS_DENIED = '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TradePilot — Acces refuse</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#080B10;color:#E2E8F0;font-family:'Inter',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;}
  .box{background:#0D1117;border:1px solid #FF4444;border-radius:16px;padding:48px 40px;text-align:center;max-width:400px;width:90%;}
  .icon{font-size:48px;margin-bottom:16px;}
  h1{font-size:22px;font-weight:700;color:#FF4444;margin-bottom:10px;}
  p{font-size:14px;color:#64748B;line-height:1.6;margin-bottom:24px;}
  .btn{display:inline-block;background:#1E293B;color:#E2E8F0;padding:12px 24px;border-radius:8px;font-weight:600;font-size:14px;text-decoration:none;}
</style>
</head>
<body>
<div class="box">
  <div class="icon">🔒</div>
  <h1>Acces refuse</h1>
  <p>{{message}}</p>
  <a href="https://discord.gg/PRrADDxCM8" class="btn">Rejoindre le Discord TradePilot</a>
</div>
</body>
</html>'''

DASHBOARD = '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TradePilot — Mes Guides</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#080B10;color:#E2E8F0;font-family:'Inter',sans-serif;min-height:100vh;}
  nav{background:#0D1117;border-bottom:1px solid #1E293B;padding:16px 32px;display:flex;align-items:center;justify-content:space-between;}
  .logo{font-size:18px;font-weight:900;color:#F5B830;letter-spacing:3px;}
  .user{font-size:13px;color:#64748B;}
  .main{max-width:800px;margin:0 auto;padding:40px 20px;}
  h1{font-size:26px;font-weight:800;color:#fff;margin-bottom:8px;}
  .sub{font-size:14px;color:#64748B;margin-bottom:32px;}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;}
  .card{background:#0D1117;border:1px solid #1E293B;border-radius:12px;padding:24px;text-decoration:none;transition:border-color .2s,transform .2s;display:block;}
  .card:hover{border-color:#F5B830;transform:translateY(-2px);}
  .card-icon{font-size:32px;margin-bottom:12px;}
  .card-title{font-size:15px;font-weight:700;color:#fff;margin-bottom:6px;}
  .card-desc{font-size:13px;color:#64748B;line-height:1.5;}
  .card.locked{opacity:.4;pointer-events:none;border-style:dashed;}
  .locked-label{font-size:11px;color:#FF4444;margin-top:8px;font-weight:600;}
  .logout{font-size:12px;color:#334155;text-decoration:none;}
  .logout:hover{color:#64748B;}
</style>
</head>
<body>
<nav>
  <div class="logo">TRADEPILOT</div>
  <div style="display:flex;align-items:center;gap:16px;">
    <span class="user">{{username}}</span>
    <a href="/guide/logout" class="logout">Deconnexion</a>
  </div>
</nav>
<div class="main">
  <h1>Mes Guides</h1>
  <p class="sub">Acces aux guides correspondant a tes offres actives.</p>
  <div class="grid">
    {{cards}}
  </div>
</div>
</body>
</html>'''

GUIDE_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TradePilot — {{title}}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  /* PROTECTION */
  * {
    -webkit-user-select: none !important;
    -moz-user-select: none !important;
    -ms-user-select: none !important;
    user-select: none !important;
  }
  body {
    background: #080B10;
    color: #E2E8F0;
    font-family: 'Inter', sans-serif;
  }
  /* Rend le contenu invisible aux logiciels de capture d'ecran via CSS isolation */
  .protected {
    isolation: isolate;
    mix-blend-mode: normal;
  }
  /* Watermark invisible sauf sur capture */
  body::after {
    content: "{{username}} — TradePilot Confidentiel";
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-30deg);
    font-size: 42px;
    color: rgba(245, 184, 48, 0.04);
    font-weight: 900;
    pointer-events: none;
    z-index: 9999;
    white-space: nowrap;
    letter-spacing: 4px;
  }
  /* NAV */
  nav {
    background: #0D1117;
    border-bottom: 1px solid #1E293B;
    padding: 14px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .logo { font-size: 16px; font-weight: 900; color: #F5B830; letter-spacing: 3px; }
  .back { font-size: 12px; color: #475569; text-decoration: none; }
  .back:hover { color: #94A3B8; }
  .user-badge {
    background: #161F2C;
    border: 1px solid #1E293B;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 11px;
    color: #64748B;
  }
  {{guide_css}}
</style>
</head>
<body class="protected" oncontextmenu="return false;" ondragstart="return false;" onselectstart="return false;">
<nav>
  <div class="logo">TRADEPILOT</div>
  <div style="display:flex;align-items:center;gap:12px;">
    <span class="user-badge">{{username}}</span>
    <a href="/guide/dashboard" class="back">← Mes guides</a>
  </div>
</nav>
<div id="guide-content">
  {{guide_content}}
</div>
<script>
  // Bloquer clic droit
  document.addEventListener('contextmenu', e => e.preventDefault());
  // Bloquer raccourcis clavier dangereux
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && ['s','p','u','a','c'].includes(e.key.toLowerCase())) {
      e.preventDefault();
      return false;
    }
    // Bloquer F12, PrintScreen
    if ([123, 44].includes(e.keyCode)) {
      e.preventDefault();
      return false;
    }
  });
  // Detecter DevTools
  let devtools = false;
  const threshold = 160;
  setInterval(() => {
    if (window.outerWidth - window.innerWidth > threshold || window.outerHeight - window.innerHeight > threshold) {
      if (!devtools) {
        devtools = true;
        document.getElementById('guide-content').innerHTML = '<div style="text-align:center;padding:80px;color:#FF4444;font-size:18px;font-weight:700;">Acces suspendu — Ferme les outils de developpement.</div>';
      }
    } else {
      devtools = false;
    }
  }, 500);
  // Bloquer impression
  window.addEventListener('beforeprint', e => { e.preventDefault(); return false; });
  // Detection capture ecran (partielle - fonctionne sur certains OS)
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      document.getElementById('guide-content').style.visibility = 'hidden';
    } else {
      document.getElementById('guide-content').style.visibility = 'visible';
    }
  });
</script>
</body>
</html>'''

# ─── CONTENU DES GUIDES ──────────────────────────────────
def get_guide_css():
    return '''
  .page { max-width: 900px; margin: 0 auto; padding: 24px 20px; }
  .cover { background: #0D1117; border: 1.5px solid #F5B830; padding: 28px 24px 20px; margin-bottom: 14px; }
  .cover-logo { font-size: 32px; font-weight: 900; color: #F5B830; letter-spacing: 4px; margin-bottom: 2px; }
  .cover-logo span { color: #94A3B8; font-size: 11px; font-weight: 400; letter-spacing: 5px; display: block; margin-top: 2px; }
  .cover-sep { height: 2px; background: linear-gradient(90deg, #F5B830, #00D4FF, transparent); margin: 14px 0; }
  .meta-table { width: 100%; border-collapse: collapse; }
  .meta-table tr:nth-child(odd) td { background: #111820; }
  .meta-table tr:nth-child(even) td { background: #0D1117; }
  .meta-key { color: #F5B830; font-weight: 700; font-size: 9px; letter-spacing: 0.5px; text-transform: uppercase; padding: 7px 10px; width: 130px; border-right: 2px solid #F5B830; }
  .meta-val { padding: 7px 12px; font-size: 10px; color: #E2E8F0; }
  .section-header { display: flex; align-items: stretch; margin: 12px 0 8px; border: 1px solid #F5B830; }
  .section-letter { background: #F5B830; color: #080B10; font-weight: 900; font-size: 16px; width: 40px; min-height: 40px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .section-text { background: #111820; padding: 7px 12px; flex: 1; }
  .section-text h2 { font-size: 12px; font-weight: 700; color: #fff; margin-bottom: 1px; }
  .section-text p { font-size: 8.5px; color: #475569; }
  .sub-header { background: #C8961F; color: #080B10; font-weight: 700; font-size: 9.5px; padding: 5px 10px; margin: 8px 0 2px; }
  .step { display: flex; align-items: stretch; border-bottom: 1px solid #1E293B; }
  .step:nth-child(odd) .step-content { background: #111820; }
  .step:nth-child(even) .step-content { background: #0D1117; }
  .step-num { background: #F5B830; color: #080B10; font-weight: 900; font-size: 11px; width: 26px; min-height: 26px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .step-content { padding: 6px 10px; flex: 1; }
  .step-title { font-weight: 600; color: #fff; font-size: 10px; margin-bottom: 2px; }
  .step-line { color: #94A3B8; font-size: 9.5px; line-height: 1.5; }
  .step-code { font-family: 'JetBrains Mono', monospace; color: #00C97A; background: #080B10; padding: 2px 6px; font-size: 9px; display: block; margin-top: 2px; }
  .alert { display: flex; align-items: stretch; margin: 6px 0; }
  .alert-label { font-size: 7px; font-weight: 700; letter-spacing: 1px; color: #080B10; padding: 0 7px; display: flex; align-items: center; justify-content: center; min-width: 48px; }
  .alert-text { background: #161F2C; padding: 7px 10px; font-size: 9.5px; color: #E2E8F0; flex: 1; line-height: 1.5; }
  .alert.warn .alert-label { background: #FF4444; } .alert.warn { border-left: 3px solid #FF4444; }
  .alert.tip .alert-label { background: #F5B830; } .alert.tip { border-left: 3px solid #F5B830; }
  .alert.ok .alert-label { background: #00C97A; color: #080B10; } .alert.ok { border-left: 3px solid #00C97A; }
  .alert.info .alert-label { background: #00D4FF; } .alert.info { border-left: 3px solid #00D4FF; }
  .photo { border: 1px dashed #333; background: #080B10; height: 65px; display: flex; align-items: center; justify-content: center; color: #333; font-size: 8.5px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; margin: 6px 0; }
  .recap { border: 1.5px solid #F5B830; border-left: 4px solid #00C97A; background: #111820; padding: 12px 14px; margin: 10px 0; }
  .recap p { font-size: 10px; color: #E2E8F0; line-height: 1.8; }
  .recap p::before { content: "✓  "; color: #00C97A; font-weight: 700; }
  .info-table { width: 100%; border-collapse: collapse; margin: 6px 0; }
  .info-table tr:nth-child(odd) td { background: #111820; }
  .info-table tr:nth-child(even) td { background: #0D1117; }
  .info-table .ik { color: #F5B830; font-weight: 700; font-size: 9px; text-transform: uppercase; padding: 6px 8px; width: 130px; border-right: 1.5px solid #F5B830; }
  .info-table .iv { padding: 6px 10px; font-size: 9.5px; color: #E2E8F0; }
  .faq-q { background: #161F2C; border-left: 3px solid #FF4444; padding: 6px 10px; font-weight: 600; color: #fff; font-size: 10px; }
  .faq-a { background: #0D1117; border-left: 3px solid #1E293B; padding: 6px 10px; color: #94A3B8; font-size: 9.5px; line-height: 1.5; border-bottom: 1px solid #1E293B; margin-bottom: 4px; }
  .params-table { width: 100%; border-collapse: collapse; margin: 8px 0; }
  .params-table th { background: #161F2C; color: #F5B830; font-size: 9px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; padding: 6px 10px; border: 1px solid #1E293B; text-align: left; }
  .params-table tr:nth-child(odd) td { background: #111820; }
  .params-table tr:nth-child(even) td { background: #0D1117; }
  .params-table td { padding: 6px 10px; font-size: 9.5px; border: 1px solid #1E293B; vertical-align: top; }
  .param-name { font-family: 'JetBrains Mono', monospace; color: #00C97A; font-weight: 600; font-size: 9px; }
  .param-default { color: #F5B830; font-family: 'JetBrains Mono', monospace; font-size: 9px; text-align: center; }
  .param-desc { color: #94A3B8; line-height: 1.4; }
  '''

LICENCE_CONTENT = '''
<div class="page">
<div class="cover">
  <div class="cover-logo">TRADEPILOT<span>GUIDE LICENCE — INSTALLATION COMPLETE</span></div>
  <div class="cover-sep"></div>
  <table class="meta-table">
    <tr><td class="meta-key">Offre</td><td class="meta-val">Licence TradePilot — 99€ paiement unique</td></tr>
    <tr><td class="meta-key">Compatibilite</td><td class="meta-val">MetaTrader 4 (MT4) et MetaTrader 5 (MT5) — Toutes paires</td></tr>
    <tr><td class="meta-key">VPS</td><td class="meta-val">Amazon AWS — Gratuit 12 mois</td></tr>
    <tr><td class="meta-key">Support</td><td class="meta-val">Discord TradePilot — #support-licence</td></tr>
    <tr><td class="meta-key">Duree</td><td class="meta-val">Environ 1h30 pour tout installer</td></tr>
  </table>
</div>

<div class="section-header"><div class="section-letter">A</div><div class="section-text"><h2>Ce que tu recois</h2><p>Fichiers inclus dans la Licence</p></div></div>
<table class="info-table">
  <tr><td class="ik">EA TradePilot</td><td class="iv">.ex4 pour MT4  /  .ex5 pour MT5 — Verrouille a ton compte</td></tr>
  <tr><td class="ik">Script Python</td><td class="iv">Surveille Telegram 24h/24 et transmet les signaux a l'EA</td></tr>
  <tr><td class="ik">Ce guide</td><td class="iv">Installation complete de A a Z</td></tr>
  <tr><td class="ik">Support</td><td class="iv">#support-licence sur Discord — reponse dans la journee</td></tr>
</table>
<div class="alert warn"><div class="alert-label">ATTENTION</div><div class="alert-text">Les fichiers sont envoyes dans ton ticket Discord apres confirmation du paiement Stripe. Verrouilles a un seul compte MT4/MT5.</div></div>

<div class="section-header"><div class="section-letter">B</div><div class="section-text"><h2>Prerequis</h2><p>Ce qu'il te faut avant de commencer</p></div></div>
<table class="info-table">
  <tr><td class="ik">Compte broker</td><td class="iv">XM  |  IC Markets  |  Pepperstone  |  Exness  |  FTMO  ou tout broker MT4/MT5</td></tr>
  <tr><td class="ik">Channel Telegram</td><td class="iv">Gratuit ou payant. Format : Paire / Direction / Entry / SL / TP</td></tr>
  <tr><td class="ik">Carte bancaire</td><td class="iv">Pour creer le compte AWS — gratuit 12 mois avec t2.micro</td></tr>
  <tr><td class="ik">Temps</td><td class="iv">Environ 1h30 pour tout installer</td></tr>
</table>


<div class="section-header"><div class="section-letter">C</div><div class="section-text"><h2>VPS Gratuit Amazon AWS</h2><p>Serveur Windows cloud — Gratuit 12 mois — obligatoire pour tourner 24h/24</p></div></div>
<div style="background:#0D1117;border:1px solid #1E293B;padding:12px 14px;margin:6px 0;">
  <p style="font-size:10px;color:#94A3B8;line-height:1.6;">Un VPS (Virtual Private Server) est un serveur Windows dans le cloud qui tourne 24h/24 sans laisser ton PC allume. Amazon AWS en propose un gratuitement pendant 12 mois. Sans VPS, le bot s'arrete quand tu eteignes ton PC.</p>
</div>
<div class="alert warn"><div class="alert-label">ATTENTION</div><div class="alert-text">Utilise UNIQUEMENT le type t2.micro. Tous les autres types sont factures immediatement meme en Free Tier.</div></div>

<div class="sub-header">C.1 — Creer ton compte AWS | aws.amazon.com</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Ouvrir aws.amazon.com dans ton navigateur</div><div class="step-line">Cliquer sur le bouton orange "Creer un compte AWS" en haut a droite de la page.</div></div></div>
<div class="photo">CAPTURE — Page d'accueil AWS avec le bouton "Creer un compte AWS"</div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Remplir les informations de base</div><div class="step-line">Email (utilise une adresse que tu consultes regulierement)</div><div class="step-line">Nom du compte AWS : TradePilot</div><div class="step-line">Mot de passe : choisir un mot de passe fort → Continuer</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Choisir le type de compte : Personnel</div><div class="step-line">Selectionner "Personnel" (pas Professionnel).</div><div class="step-line">Remplir : prenom, nom, numero de telephone, pays, adresse complete.</div></div></div>
<div class="photo">CAPTURE — Formulaire type de compte avec "Personnel" selectionne</div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Entrer ta carte bancaire</div><div class="step-line">Entrer les informations de ta carte bancaire.</div><div class="step-line">Une charge de 1$ (environ 0.90€) apparait sur ta carte puis est remboursee automatiquement.</div><div class="step-line">C'est uniquement pour verifier que la carte est valide — aucun debit pendant 12 mois avec t2.micro.</div></div></div>
<div class="photo">CAPTURE — Formulaire de carte bancaire AWS</div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Verification par SMS</div><div class="step-line">Choisir "Message texte (SMS)".</div><div class="step-line">Entrer ton numero de telephone avec l'indicatif pays (+33 pour la France).</div><div class="step-line">Entrer le code a 4 chiffres recu par SMS → Continuer.</div></div></div>
<div class="photo">CAPTURE — Ecran de verification SMS</div>
<div class="step"><div class="step-num">6</div><div class="step-content"><div class="step-title">Choisir le plan gratuit</div><div class="step-line">Sur la page de choix du plan → selectionner "Gratuit (Free)".</div><div class="step-line">Cliquer "Terminer l'inscription" → puis "Acceder a la console AWS".</div></div></div>
<div class="photo">CAPTURE — Page de choix du plan avec "Gratuit" selectionne</div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">Compte AWS cree — tu es maintenant dans la console Amazon Web Services.</div></div>

<div class="sub-header">C.2 — Lancer le serveur Windows | Console AWS → EC2</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Aller dans EC2</div><div class="step-line">Dans la barre de recherche en haut de la console AWS → taper "EC2" → cliquer sur le resultat "EC2 - Virtual Servers in the Cloud".</div></div></div>
<div class="photo">CAPTURE — Console AWS avec EC2 dans la barre de recherche</div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Lancer une instance</div><div class="step-line">Sur la page EC2 → cliquer sur le bouton orange "Lancer une instance" au centre de la page.</div></div></div>
<div class="photo">CAPTURE — Page EC2 avec le bouton "Lancer une instance"</div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Nommer le serveur</div><div class="step-line">Dans le champ "Nom et balises" → taper exactement : TradePilot-Bot</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Choisir l'image Windows Server 2022</div><div class="step-line">Dans la section "Images d'application et de systeme d'exploitation" → cliquer sur "Windows".</div><div class="step-line">Selectionner "Microsoft Windows Server 2022 Base".</div><div class="step-line">Verifier que "Free tier eligible" apparait en dessous.</div></div></div>
<div class="photo">CAPTURE — Selection de Windows Server 2022 avec "Free tier eligible" visible</div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Choisir le type t2.micro — NE JAMAIS CHANGER</div><div class="step-line">Dans "Type d'instance" → selectionner "t2.micro".</div><div class="step-line">Verifier "Free tier eligible" → sinon chercher t2.micro dans la liste.</div><div class="step-line">NE JAMAIS selectionner un autre type — ils sont tous factures immediatement.</div></div></div>
<div class="photo">CAPTURE — Type d'instance t2.micro selectionne avec "Free tier eligible"</div>
<div class="step"><div class="step-num">6</div><div class="step-content"><div class="step-title">Creer la paire de cles</div><div class="step-line">Dans "Paire de cles (connexion)" → cliquer "Creer une paire de cles".</div><div class="step-line">Nom : tradepilot-key | Type : RSA | Format : .pem → Cliquer "Creer une paire de cles".</div><div class="step-line">Le fichier tradepilot-key.pem se telecharge automatiquement.</div><div class="step-line">CONSERVER CE FICHIER PRECIEUSEMENT — sans lui tu ne peux pas recuperer le mot de passe.</div></div></div>
<div class="photo">CAPTURE — Fenetre de creation de paire de cles avec les bons parametres</div>
<div class="step"><div class="step-num">7</div><div class="step-content"><div class="step-title">Configurer le reseau</div><div class="step-line">Dans "Parametres reseau" → cocher les 3 cases :</div><div class="step-line">✓ Autoriser le trafic RDP depuis Internet</div><div class="step-line">✓ Autoriser le trafic HTTP</div><div class="step-line">✓ Autoriser le trafic HTTPS</div></div></div>
<div class="step"><div class="step-num">8</div><div class="step-content"><div class="step-title">Lancer l'instance</div><div class="step-line">Verifier dans le resume a droite : 1 instance | t2.micro | Windows.</div><div class="step-line">Cliquer le bouton orange "Lancer l'instance" → cliquer "Afficher toutes les instances".</div><div class="step-line">Attendre 3 a 5 minutes → le statut passe de "En attente" a "En cours d'execution".</div></div></div>
<div class="photo">CAPTURE — Instance avec statut "En cours d'execution" et point vert</div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">Serveur Windows cree et en cours d'execution sur AWS.</div></div>

<div class="sub-header">C.3 — Recuperer le mot de passe | Instance AWS</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Ouvrir les details de l'instance</div><div class="step-line">Cliquer sur l'ID de l'instance (ex : i-0abc123456789...).</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Cliquer sur "Se connecter"</div><div class="step-line">Cliquer le bouton "Se connecter" en haut de la page de details.</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Onglet "Client RDP"</div><div class="step-line">Cliquer sur l'onglet "Client RDP" (Remote Desktop Protocol).</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Dechiffrer le mot de passe</div><div class="step-line">Cliquer "Obtenir le mot de passe".</div><div class="step-line">Cliquer "Parcourir" → selectionner le fichier tradepilot-key.pem.</div><div class="step-line">Cliquer "Dechiffrer le mot de passe".</div></div></div>
<div class="photo">CAPTURE — Page Client RDP avec le mot de passe dechiffre visible</div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Copier les identifiants</div><div class="step-line">Note quelque part ces 3 informations :</div><div class="step-line">→ Nom DNS public (ex : ec2-XX-XX-XX-XX.compute-1.amazonaws.com)</div><div class="step-line">→ Nom d'utilisateur : Administrator</div><div class="step-line">→ Mot de passe : (le copier en entier, il est long)</div></div></div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">Identifiants recuperes — on peut maintenant se connecter au serveur.</div></div>

<div class="sub-header">C.4 — Connexion Bureau a distance | Windows → mstsc</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Ouvrir la connexion Bureau a distance</div><div class="step-line">Sur ton PC Windows : appuyer sur les touches Windows + R simultanement.</div><div class="step-line">Dans la fenetre "Executer" → taper : mstsc → appuyer sur Entree.</div></div></div>
<div class="photo">CAPTURE — Fenetre "Executer" avec mstsc tape dedans</div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Entrer l'adresse du serveur</div><div class="step-line">Dans le champ "Ordinateur" → coller le Nom DNS public copie a l'etape precedente.</div><div class="step-line">Cliquer "Connexion".</div></div></div>
<div class="photo">CAPTURE — Fenetre Bureau a distance avec le Nom DNS public colle</div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Accepter l'avertissement de securite</div><div class="step-line">Une fenetre d'avertissement apparait → cliquer "Oui" pour continuer.</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Se connecter avec les identifiants</div><div class="step-line">Nom d'utilisateur : Administrator</div><div class="step-line">Mot de passe : (celui copie a l'etape C.3)</div><div class="step-line">Cliquer "OK".</div></div></div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Attendre le chargement du serveur</div><div class="step-line">Attendre 30 a 60 secondes — Windows se charge.</div><div class="step-line">Le Bureau Windows du serveur AWS apparait a l'ecran.</div><div class="step-line">Tout ce qu'on fait maintenant se passe SUR CE SERVEUR — pas sur ton PC.</div></div></div>
<div class="photo">CAPTURE — Bureau Windows du serveur AWS visible a l'ecran</div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">Connecte au serveur AWS. Toutes les etapes suivantes se font SUR CE SERVEUR dans la fenetre Bureau a distance.</div></div>
<div class="alert tip"><div class="alert-label">CONSEIL</div><div class="alert-text">Tu peux copier-coller du texte entre ton PC et le serveur AWS avec Ctrl+C / Ctrl+V. Pratique pour coller des commandes dans PowerShell.</div></div>

<div class="section-header"><div class="section-letter">D</div><div class="section-text"><h2>MetaTrader 4 (MT4)</h2><p>Installation sur le serveur AWS</p></div></div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Telecharger MT4 depuis ton broker</div><div class="step-line">Site du broker → telecharger MetaTrader 4. Cela configure automatiquement les serveurs de connexion.</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Installer MT4</div><div class="step-line">Lancer le .exe → Suivant → Installer → Terminer. MT4 s'ouvre automatiquement.</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Se connecter au compte</div><div class="step-line">Fichier → Connexion a un compte de trading → Numero de compte | Mot de passe | Serveur → Connexion</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Ouvrir un graphique</div><div class="step-line">Fichier → Nouvelle fenetre → chercher la paire souhaitee → selectionner → periode M5</div></div></div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Activer Trading automatique</div><div class="step-line">Cliquer "Trading automatique" en haut → doit etre VERT</div></div></div>
<div class="photo">AJOUTER CAPTURE — MT4 connecte, Trading automatique VERT</div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">MT4 installe et connecte.</div></div>

<div class="section-header"><div class="section-letter">E</div><div class="section-text"><h2>MetaTrader 5 (MT5)</h2><p>Si ton broker propose MT5 — sinon passer a l'etape F</p></div></div>
<div class="alert info"><div class="alert-label">INFO</div><div class="alert-text">MT4 est recommande pour debuter. MT5 supporte plus d'actifs (actions, crypto, futures). Le fichier EA est different : .ex5 au lieu de .ex4 — dossier MQL5 au lieu de MQL4.</div></div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Telecharger MT5 depuis ton broker</div><div class="step-line">Site du broker → MetaTrader 5 → telecharger et installer.</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Se connecter</div><div class="step-line">Fichier → Connexion → chercher broker → Numero de compte | Mot de passe | Connexion</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Ouvrir graphique + M5</div><div class="step-line">Navigateur → Instruments → paire → double-clic → barre periodes → M5</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Activer Trading automatique</div><div class="step-line">Cliquer "Trading automatique" → VERT | Outils → Options → Expert Advisors → Autoriser le trading automatique</div></div></div>
<div class="photo">AJOUTER CAPTURE — MT5 connecte, Trading automatique VERT</div>

<div class="section-header"><div class="section-letter">F</div><div class="section-text"><h2>EA TradePilot</h2><p>Installation sur MT4 ou MT5</p></div></div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Ouvrir le repertoire des donnees</div><div class="step-line">MetaTrader → Fichier → Ouvrir le repertoire des donnees</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Aller dans Experts</div><div class="step-line">MT4 : MQL4 → Experts | MT5 : MQL5 → Experts</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Copier le fichier EA</div><div class="step-line">MT4 : glisser TradePilot_EA.ex4 | MT5 : glisser TradePilot_EA.ex5 — depuis le PC via Bureau a distance</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Actualiser MetaTrader</div><div class="step-line">Navigateur → clic droit → Actualiser → l'EA TradePilot apparait dans Expert Advisors</div></div></div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Glisser l'EA sur le graphique</div><div class="step-line">Navigateur → Expert Advisors → TradePilot_EA → glisser sur le graphique</div></div></div>
<div class="step"><div class="step-num">6</div><div class="step-content"><div class="step-title">Configurer</div><div class="step-line">Onglet "General" → cocher "Autoriser le trading automatique" | Onglet "Entrees" → parametres | OK</div></div></div>
<div class="step"><div class="step-num">7</div><div class="step-content"><div class="step-title">Verifier</div><div class="step-line">Nom TradePilot_EA en haut a droite du graphique | Smiley JAUNE | Trading automatique VERT</div></div></div>
<div class="photo">AJOUTER CAPTURE — EA actif, smiley jaune</div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">EA TradePilot actif sur le graphique.</div></div>

<div class="section-header"><div class="section-letter">G</div><div class="section-text"><h2>Script Python</h2><p>Le pont entre Telegram et MetaTrader</p></div></div>
<div class="sub-header">G.1 — Installer Python 3.11</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Telecharger Python 3.11</div><div class="step-line">python.org/downloads → Python 3.11.9 → telecharger</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Installer — cocher Add Python to PATH</div><div class="step-line">AVANT "Install Now" → cocher "Add Python to PATH" → Install Now → Close</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Verifier</div><div class="step-line code">python --version   →   Python 3.11.9</div></div></div>
<div class="photo">AJOUTER CAPTURE — python --version = Python 3.11.9</div>

<div class="sub-header">G.2 — Configurer le script</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Creer le dossier</div><div class="step-line">Bureau du serveur → clic droit → Nouveau dossier → TradePilot-Bot</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Copier le script</div><div class="step-line">Glisser tradepilot_signal.py depuis le PC dans la fenetre Bureau a distance</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Configurer</div><div class="step-line">Clic droit → Notepad → trouver la ligne CHANNEL et BOT_TOKEN → remplir avec les tiennes → Ctrl+S</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Installer les dependances</div><div class="step-line code">python -m pip install telethon MetaTrader5</div></div></div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Lancer et tester</div><div class="step-line code">cd Desktop\\TradePilot-Bot</div><div class="step-line code">python tradepilot_signal.py</div><div class="step-line">Envoyer un signal test sur Telegram → l'ordre s'ouvre sur MT4/MT5</div></div></div>
<div class="photo">AJOUTER CAPTURE — Signal detecte, ordre ouvert sur MT4/MT5</div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">Systeme operationnel — signal Telegram → ordre MT4/MT5 en moins d'1 seconde.</div></div>

<div class="section-header"><div class="section-letter">H</div><div class="section-text"><h2>NSSM — 24h/24</h2><p>Service Windows permanent</p></div></div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Telecharger NSSM</div><div class="step-line code">curl -o nssm.zip https://nssm.cc/release/nssm-2.24.zip</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Extraire</div><div class="step-line code">Expand-Archive -Path nssm.zip -DestinationPath C:\\nssm</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Installer comme service</div><div class="step-line code">C:\\nssm\\\nssm-2.24\\win64\\\nssm.exe install TradePilotSignal "C:\\Python311\\python.exe" "C:\\Users\\Administrator\\Desktop\\TradePilot-Bot\tradepilot_signal.py"</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Demarrer</div><div class="step-line code">C:\\nssm\\\nssm-2.24\\win64\\\nssm.exe start TradePilotSignal</div></div></div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Verifier</div><div class="step-line">Fermer Bureau a distance → attendre 2 min → envoyer signal test → l'ordre s'ouvre toujours</div></div></div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">Le systeme tourne 24h/24 automatiquement — meme PC eteint.</div></div>

<div class="recap">
  <p>VPS AWS cree et configure</p>
  <p>MT4 ou MT5 installe et connecte au compte broker</p>
  <p>EA TradePilot actif sur le graphique</p>
  <p>Script Python connecte a Telegram</p>
  <p>NSSM — redemarrage automatique en permanence</p>
</div>

<div class="section-header"><div class="section-letter">I</div><div class="section-text"><h2>Parametres avances de l'EA</h2><p>Double-clic sur l'EA → Onglet Entrees</p></div></div>
<table class="params-table">
  <tr><th>Parametre</th><th>Defaut</th><th>Description</th></tr>
  <tr><td class="param-name">BaseLot</td><td class="param-default">0.01</td><td class="param-desc">Taille de position. 0.01 = micro-lot — recommande pour debuter.</td></tr>
  <tr><td class="param-name">TP_Pips</td><td class="param-default">30.0</td><td class="param-desc">Pips de Take Profit.</td></tr>
  <tr><td class="param-name">SL_Pips</td><td class="param-default">50.0</td><td class="param-desc">Pips de Stop Loss.</td></tr>
  <tr><td class="param-name">RSI_Period</td><td class="param-default">14</td><td class="param-desc">Periode du RSI pour les signaux d'entree.</td></tr>
  <tr><td class="param-name">EMA_Fast</td><td class="param-default">50</td><td class="param-desc">EMA rapide pour la tendance.</td></tr>
  <tr><td class="param-name">EMA_Slow</td><td class="param-default">200</td><td class="param-desc">EMA lente pour la tendance.</td></tr>
  <tr><td class="param-name">RecoveryTrigger</td><td class="param-default">20.0</td><td class="param-desc">Perte en $ qui declenche le mode recuperation.</td></tr>
  <tr><td class="param-name">HardStop</td><td class="param-default">100.0</td><td class="param-desc">Perte maximale en $ — arret complet.</td></tr>
</table>
<div class="alert tip"><div class="alert-label">CONSEIL</div><div class="alert-text">Commence avec BaseLot = 0.01. Ne depasse jamais 1-2% de ton capital par trade.</div></div>

<div class="section-header"><div class="section-letter">J</div><div class="section-text"><h2>FAQ</h2><p>Questions frequentes</p></div></div>
<div class="faq-q">Le smiley sur MT4/MT5 est rouge</div>
<div class="faq-a">L'EA n'est pas autorise. Cliquer "Trading automatique" en haut (vert). MT5 : Outils → Options → Expert Advisors → Autoriser.</div>
<div class="faq-q">Le script s'arrete la nuit</div>
<div class="faq-a">NSSM n'est pas installe. Suivre la Partie H pour installer le service permanent.</div>
<div class="faq-q">L'ordre ne s'ouvre pas</div>
<div class="faq-a">Verifier MT4/MT5 ouvert | EA sur le graphique | Trading automatique vert | Onglet "Experts" pour les erreurs.</div>
<div class="faq-q">Puis-je utiliser sur plusieurs comptes ?</div>
<div class="faq-a">Non — verrouille a un seul compte. Pour un deuxieme compte, ouvrir un ticket Discord.</div>
<div class="faq-q">AWS m'a facture</div>
<div class="faq-a">Verifier que seul t2.micro est utilise. Facturation AWS → doit etre 0$.</div>
<div class="faq-q">Comment mettre a jour l'EA ?</div>
<div class="faq-a">Remplacer l'ancien .ex4/.ex5 dans Experts, redemarrer MetaTrader, reglisser l'EA.</div>
</div>
'''

SETUP_CONTENT = '''
<div class="page">
<div class="cover" style="border-color:#00C97A;">
  <div class="cover-logo">TRADEPILOT<span>GUIDE SETUP PRO — INSTALLATION COMPLETE</span></div>
  <div class="cover-sep" style="background:linear-gradient(90deg,#00C97A,#F5B830,transparent);"></div>
  <table class="meta-table">
    <tr><td class="meta-key" style="color:#00C97A;border-right-color:#00C97A;">Offre</td><td class="meta-val">Setup Pro — 200€ paiement unique</td></tr>
    <tr><td class="meta-key" style="color:#00C97A;border-right-color:#00C97A;">Service</td><td class="meta-val">Installation complete faite par TradePilot a distance</td></tr>
    <tr><td class="meta-key" style="color:#00C97A;border-right-color:#00C97A;">Duree</td><td class="meta-val">30 a 60 minutes</td></tr>
    <tr><td class="meta-key" style="color:#00C97A;border-right-color:#00C97A;">Support</td><td class="meta-val">Discord — #support-setup — Prioritaire 30 jours</td></tr>
  </table>
</div>

<div class="section-header" style="border-color:#00C97A;"><div class="section-letter" style="background:#00C97A;">A</div><div class="section-text"><h2>Ce qui est installe</h2><p>Tout ce que je configure lors de la session</p></div></div>
<table class="info-table">
  <tr><td class="ik">Python 3.11</td><td class="iv">Installe sur ton PC ou VPS avec les bonnes dependances</td></tr>
  <tr><td class="ik">MT4 ou MT5</td><td class="iv">Installe, connecte a ton broker, graphique configure</td></tr>
  <tr><td class="ik">EA TradePilot</td><td class="iv">Installe et actif — smiley jaune, trading automatique vert</td></tr>
  <tr><td class="ik">Script Python</td><td class="iv">Configure avec ton channel Telegram</td></tr>
  <tr><td class="ik">NSSM</td><td class="iv">Service permanent — tourne 24h/24 meme apres redemarrage</td></tr>
  <tr><td class="ik">Test en direct</td><td class="iv">Premier signal teste en ta presence — on valide ensemble</td></tr>
</table>
<div class="alert ok"><div class="alert-label">INCLUS</div><div class="alert-text">Support prioritaire 30 jours — si quelque chose ne fonctionne plus, je repare immediatement.</div></div>

<div class="section-header" style="border-color:#00C97A;"><div class="section-letter" style="background:#00C97A;">B</div><div class="section-text"><h2>Ce que tu dois preparer</h2><p>A faire AVANT la session pour qu'on aille vite</p></div></div>

<div class="sub-header">B.1 — Compte broker</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Avoir un compte broker MT4 ou MT5</div><div class="step-line">XM | IC Markets | Pepperstone | Exness | FTMO ou autre broker proposant MT4/MT5</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Note tes identifiants</div><div class="step-line">Numero de compte MT4/MT5 | Mot de passe | Nom du serveur (ex: XM-Real3)</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Compte demo recommande pour commencer</div><div class="step-line">Si tu debutes, ouvre un compte demo — zero risque pendant l'apprentissage.</div></div></div>

<div class="sub-header">B.2 — Channel Telegram de signaux</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Avoir acces a un channel Telegram</div><div class="step-line">Gratuit ou payant. Format requis : Paire | Direction | Entry | SL | TP</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Connaitre le nom ou ID du channel</div><div class="step-line">Nom public @channel ou ID numerique du channel prive</div></div></div>

<div class="sub-header">B.3 — TeamViewer ou AnyDesk — OBLIGATOIRE</div>
<div class="alert warn"><div class="alert-label">ATTENTION</div><div class="alert-text">Sans TeamViewer ou AnyDesk la session ne peut pas avoir lieu. A installer AVANT de me contacter.</div></div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Telecharger TeamViewer (recommande)</div><div class="step-line code">teamviewer.com</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Ou AnyDesk</div><div class="step-line code">anydesk.com</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Preparer ton ID et mot de passe</div><div class="step-line">Lance TeamViewer/AnyDesk → note l'ID et le mot de passe → tu me les envoies dans le ticket Discord.</div></div></div>


<div class="section-header" style="border-color:#00C97A;"><div class="section-letter" style="background:#00C97A;">C</div><div class="section-text"><h2>VPS Gratuit AWS — Optionnel</h2><p>Si tu veux que le bot tourne 24h/24 sans laisser ton PC allume</p></div></div>
<div style="background:#0D1117;border:1px solid #1E293B;padding:12px 14px;margin:6px 0;">
  <p style="font-size:10px;color:#94A3B8;line-height:1.6;">Si tu veux que ton systeme tourne meme PC eteint, on cree ensemble un VPS Amazon AWS gratuit (12 mois) lors de la session Setup Pro. Tu n'as rien a faire a l'avance — je m'en occupe pendant la session.</p>
</div>
<div class="alert info"><div class="alert-label">INFO</div><div class="alert-text">Le VPS AWS est INCLUS dans le Setup Pro — je le configure pendant la session si tu le veux. Dis-le moi dans ton ticket Discord avant qu'on commence.</div></div>

<div class="sub-header">Ce dont j'ai besoin si tu veux le VPS</div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Creer un compte AWS avant la session (recommande)</div><div class="step-line">Va sur aws.amazon.com → "Creer un compte AWS" → suis les etapes.</div><div class="step-line">Tu auras besoin d'une carte bancaire pour la verification (charge de 1$ remboursee).</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Ou laisser tomber le compte AWS</div><div class="step-line">Je peux installer tout sur ton PC directement. Dans ce cas le bot tourne seulement quand ton PC est allume.</div></div></div>
<div class="alert tip"><div class="alert-label">CONSEIL</div><div class="alert-text">Cree le compte AWS avant la session → on gagne du temps. Sinon on le fait ensemble — compte environ 30 min supplementaires.</div></div>

<div class="section-header" style="border-color:#00C97A;"><div class="section-letter" style="background:#00C97A;">D</div><div class="section-text"><h2>Deroulement de la session</h2><p>Ce qui se passe de A a Z</p></div></div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Ouvrir un ticket dans #ouvrir-un-ticket</div><div class="step-line">Cliquer le bouton dans le salon Discord.</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Envoyer la confirmation Stripe</div><div class="step-line">Coller la confirmation de paiement dans le ticket.</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Planifier la session</div><div class="step-line">On trouve un creneau ensemble. Je te contacte a l'heure prevue.</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Lancer TeamViewer/AnyDesk</div><div class="step-line">Tu m'envoies l'ID et le mot de passe dans le ticket. Je me connecte.</div></div></div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Installation complete</div><div class="step-line">Je m'occupe de tout : Python, MT4/MT5, EA, script, NSSM. Tu regardes.</div></div></div>
<div class="step"><div class="step-num">6</div><div class="step-content"><div class="step-title">Test en direct</div><div class="step-line">On envoie un signal test → l'ordre s'ouvre automatiquement sur MT4/MT5.</div></div></div>
<div class="step"><div class="step-num">7</div><div class="step-content"><div class="step-title">Systeme operationnel</div><div class="step-line">Ton bot tourne 24h/24. Tu n'as plus rien a faire sauf trader.</div></div></div>
<div class="alert ok"><div class="alert-label">OK</div><div class="alert-text">Installation terminee — ton systeme est operationnel 24h/24.</div></div>

<div class="section-header" style="border-color:#00C97A;"><div class="section-letter" style="background:#00C97A;">E</div><div class="section-text"><h2>FAQ</h2><p>Questions frequentes</p></div></div>
<div class="faq-q">Je dois avoir des connaissances techniques ?</div>
<div class="faq-a">Non — je m'occupe de tout. Tu regardes, tu n'as rien a faire. La seule chose requise c'est TeamViewer installe et tes identifiants broker.</div>
<div class="faq-q">Ca prend combien de temps ?</div>
<div class="faq-a">30 a 60 minutes selon ta configuration et ta connexion internet. Prevois 1 heure.</div>
<div class="faq-q">Sur quel PC ?</div>
<div class="faq-a">Ton PC personnel ou un VPS. Si tu veux que ca tourne 24h/24 sans PC allume, on cree un VPS AWS gratuit pendant la session.</div>
<div class="faq-q">Tu vois mon argent ?</div>
<div class="faq-a">Non. TeamViewer donne acces a l'ecran uniquement. Ton compte broker, ton argent et tes trades restent entierement sous ton controle.</div>
<div class="faq-q">Que se passe-t-il si ca ne marche plus apres ?</div>
<div class="faq-a">30 jours de support prioritaire. Si quelque chose ne fonctionne plus → #support-setup → je repare.</div>
</div>
'''

SIGNAL_CONTENT = '''
<div class="page">
<div class="cover" style="border-color:#00D4FF;">
  <div class="cover-logo">TRADEPILOT<span>GUIDE SIGNAL VIP — SIGNAUX EN TEMPS REEL</span></div>
  <div class="cover-sep" style="background:linear-gradient(90deg,#00D4FF,#F5B830,transparent);"></div>
  <table class="meta-table">
    <tr><td class="meta-key" style="color:#00D4FF;border-right-color:#00D4FF;">Offre</td><td class="meta-val">Signal VIP — 59.99€/mois resiliable a tout moment</td></tr>
    <tr><td class="meta-key" style="color:#00D4FF;border-right-color:#00D4FF;">Acces</td><td class="meta-val">Channel Telegram prive + #signaux-live Discord</td></tr>
    <tr><td class="meta-key" style="color:#00D4FF;border-right-color:#00D4FF;">Actifs</td><td class="meta-val">Toutes paires Forex, Or, Indices selon les opportunites</td></tr>
    <tr><td class="meta-key" style="color:#00D4FF;border-right-color:#00D4FF;">Support</td><td class="meta-val">Discord — #support-vip — reponse dans la journee</td></tr>
  </table>
</div>

<div class="section-header" style="border-color:#00D4FF;"><div class="section-letter" style="background:#00D4FF;">A</div><div class="section-text"><h2>Ce que tu recois</h2><p>Contenu de l'abonnement Signal VIP</p></div></div>
<table class="info-table">
  <tr><td class="ik" style="color:#00D4FF;border-right-color:#00D4FF;">Telegram prive</td><td class="iv">Channel prive avec signaux live en temps reel — invitation dans ton ticket Discord</td></tr>
  <tr><td class="ik" style="color:#00D4FF;border-right-color:#00D4FF;">#signaux-live</td><td class="iv">Meme contenu sur Discord — tu choisis Telegram, Discord ou les deux</td></tr>
  <tr><td class="ik" style="color:#00D4FF;border-right-color:#00D4FF;">#resultats-du-jour</td><td class="iv">Tous les resultats publies chaque jour — transparence totale, gains et pertes</td></tr>
  <tr><td class="ik" style="color:#00D4FF;border-right-color:#00D4FF;">Analyses</td><td class="iv">Contexte marche quotidien — pourquoi ce setup, niveaux cles, biais du jour</td></tr>
</table>
<div class="alert info"><div class="alert-label">INFO</div><div class="alert-text">Tu peux copier les signaux manuellement sur MT4/MT5 OU les automatiser avec la Licence TradePilot. La Licence est vendue separement.</div></div>

<div class="alert info"><div class="alert-label">INFO</div><div class="alert-text">Si tu veux AUTOMATISER les signaux (pas les copier manuellement), tu auras besoin d'un VPS pour faire tourner le script 24h/24. Voir la Licence TradePilot pour l'installation complete.</div></div>


<div class="section-header" style="border-color:#00D4FF;"><div class="section-letter" style="background:#00D4FF;">B</div><div class="section-text"><h2>Lire un signal</h2><p>Comprendre chaque element</p></div></div>
<div style="background:#080B10;border:1.5px solid #00D4FF;padding:16px;margin:8px 0;font-family:'JetBrains Mono',monospace;">
  <div style="color:#00D4FF;font-size:9px;font-weight:600;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;">Exemple de signal BUY</div>
  <div style="font-size:13px;margin-bottom:4px;"><span style="color:#F5B830;font-weight:700;">XAUUSD</span>  <span style="color:#00C97A;font-weight:700;">BUY</span></div>
  <div style="font-size:11px;margin-bottom:3px;"><span style="color:#475569;">Entry  : </span><span style="color:#fff;font-weight:600;">2 341.50</span></div>
  <div style="font-size:11px;margin-bottom:3px;"><span style="color:#475569;">SL     : </span><span style="color:#FF4444;">2 325.00</span></div>
  <div style="font-size:11px;margin-bottom:3px;"><span style="color:#475569;">TP1    : </span><span style="color:#00C97A;">2 358.00</span></div>
  <div style="font-size:11px;margin-bottom:3px;"><span style="color:#475569;">TP2    : </span><span style="color:#00C97A;">2 370.00</span></div>
  <div style="font-size:11px;"><span style="color:#475569;">Lots   : </span><span style="color:#fff;">0.01</span> <span style="color:#475569;">(ajuster selon ton capital)</span></div>
</div>
<table class="params-table">
  <tr><th>Element</th><th>Exemple</th><th>Signification</th></tr>
  <tr><td class="param-name">Paire</td><td class="param-default">XAUUSD</td><td class="param-desc">L'actif trade. Peut etre n'importe quelle paire Forex, Or, Indice...</td></tr>
  <tr><td class="param-name">BUY/SELL</td><td class="param-default">BUY</td><td class="param-desc">BUY = pari a la hausse. SELL = pari a la baisse.</td></tr>
  <tr><td class="param-name">Entry</td><td class="param-default">2341.50</td><td class="param-desc">Prix d'ouverture de la position.</td></tr>
  <tr><td class="param-name">SL</td><td class="param-default">2325.00</td><td class="param-desc">Stop Loss — perte coupee automatiquement. OBLIGATOIRE.</td></tr>
  <tr><td class="param-name">TP1</td><td class="param-default">2358.00</td><td class="param-desc">Premier objectif de profit — fermer la moitie de la position ici.</td></tr>
  <tr><td class="param-name">TP2</td><td class="param-default">2370.00</td><td class="param-desc">Deuxieme objectif — laisser courir le reste.</td></tr>
</table>

<div class="section-header" style="border-color:#00D4FF;"><div class="section-letter" style="background:#00D4FF;">C</div><div class="section-text"><h2>Copier un signal sur MT4</h2><p>Pour ceux qui copient manuellement</p></div></div>
<div class="alert info"><div class="alert-label">INFO</div><div class="alert-text">Si tu as la Licence TradePilot, les ordres s'ouvrent automatiquement — tu n'as rien a faire.</div></div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Ouvrir MT4 sur la bonne paire</div><div class="step-line">Etre sur le graphique de la paire signalee, periode M5.</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Ouvrir un nouvel ordre</div><div class="step-line">F9 ou bouton "Nouveau Ordre" en haut de MT4.</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Remplir les champs</div><div class="step-line">Symbole : paire du signal | Lots : 0.01 | Stop Loss : SL du signal | Take Profit : TP1</div></div></div>
<div class="step"><div class="step-num">4</div><div class="step-content"><div class="step-title">Ouvrir l'ordre</div><div class="step-line">Cliquer "Achat" (BUY) ou "Vente" (SELL) → ordre visible dans "Transactions" en bas.</div></div></div>
<div class="step"><div class="step-num">5</div><div class="step-content"><div class="step-title">Gestion de la position</div><div class="step-line">Quand TP1 atteint → fermer la moitie → deplacer SL au prix d'entree → laisser courir vers TP2.</div></div></div>
<div class="step"><div class="step-num">6</div><div class="step-content"><div class="step-title">Si signal "Fermer" envoye</div><div class="step-line">Clic droit sur la position → "Fermer l'ordre" → sortir immediatement.</div></div></div>

<div class="section-header" style="border-color:#00D4FF;"><div class="section-letter" style="background:#00D4FF;">D</div><div class="section-text"><h2>Gestion du risque</h2><p>Indispensable — meme avec les meilleurs signaux</p></div></div>
<div class="alert warn"><div class="alert-label">ATTENTION</div><div class="alert-text">Ne jamais risquer plus de 1 a 2% du capital par trade. Les signaux sont informatifs — le trading comporte des risques.</div></div>
<table class="params-table">
  <tr><th>Capital</th><th>Lot recommande</th><th>Risque ~1.5%</th></tr>
  <tr><td class="param-desc">500€</td><td class="param-default">0.01</td><td class="param-desc" style="color:#00C97A;">~7.50€</td></tr>
  <tr><td class="param-desc">1 000€</td><td class="param-default">0.02</td><td class="param-desc" style="color:#00C97A;">~15€</td></tr>
  <tr><td class="param-desc">2 500€</td><td class="param-default">0.05</td><td class="param-desc" style="color:#F5B830;">~37.50€</td></tr>
  <tr><td class="param-desc">5 000€</td><td class="param-default">0.10</td><td class="param-desc" style="color:#F5B830;">~75€</td></tr>
  <tr><td class="param-desc">10 000€</td><td class="param-default">0.20</td><td class="param-desc" style="color:#FF4444;">~150€</td></tr>
</table>

<div class="section-header" style="border-color:#00D4FF;"><div class="section-letter" style="background:#00D4FF;">E</div><div class="section-text"><h2>Tes acces</h2><p>Ou trouver les signaux</p></div></div>
<div class="step"><div class="step-num">1</div><div class="step-content"><div class="step-title">Rejoindre le channel Telegram prive</div><div class="step-line">Lien d'invitation dans ton ticket Discord apres confirmation du paiement.</div></div></div>
<div class="step"><div class="step-num">2</div><div class="step-content"><div class="step-title">Activer les notifications Telegram</div><div class="step-line">Channel → nom en haut → Notifications → Tous les messages</div></div></div>
<div class="step"><div class="step-num">3</div><div class="step-content"><div class="step-title">Activer les notifications Discord</div><div class="step-line">Clic droit sur #signaux-live → Notifications → Tous les messages</div></div></div>

<div class="section-header" style="border-color:#00D4FF;"><div class="section-letter" style="background:#00D4FF;">F</div><div class="section-text"><h2>FAQ</h2><p>Questions frequentes</p></div></div>
<div class="faq-q">Combien de signaux par semaine ?</div>
<div class="faq-a">En moyenne 3 a 7 signaux selon les conditions de marche. La qualite prime sur la quantite.</div>
<div class="faq-q">Je peux automatiser les signaux ?</div>
<div class="faq-a">Oui avec la Licence TradePilot (99€) — le script detecte chaque signal et l'execute automatiquement sur MT4/MT5.</div>
<div class="faq-q">Comment resilier ?</div>
<div class="faq-a">Depuis ton espace Stripe en 1 clic ou ticket Discord. Resiliation immediate, acces jusqu'a fin du mois paye.</div>
<div class="faq-q">Que faire si je rate un signal ?</div>
<div class="faq-a">Ne jamais entrer en retard sur un signal si le prix a deja bouge. Attendre le prochain.</div>
<div class="faq-q">Les signaux sont des conseils financiers ?</div>
<div class="faq-a">Non — informatifs uniquement. Tu restes seul responsable de tes decisions de trading.</div>
</div>
'''

# ─── ROUTES ──────────────────────────────────────────────
@app.route('/guide/login')
def guide_login():
    return LOGIN_PAGE

@app.route('/auth/discord')
def auth_discord():
    state = secrets.token_hex(16)
    session['oauth_state'] = state
    params = {
        'client_id':     DISCORD_CLIENT_ID,
        'redirect_uri':  DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope':         OAUTH_SCOPES,
        'state':         state,
    }
    url = f"{DISCORD_API}/oauth2/authorize?" + '&'.join(f'{k}={v}' for k,v in params.items())
    return redirect(url)

@app.route('/auth/callback')
def auth_callback():
    code  = request.args.get('code')
    state = request.args.get('state')

    if not code or state != session.get('oauth_state'):
        return ACCESS_DENIED.replace('{{message}}', 'Session invalide — reessaie.')

    # Echange du code contre un token
    token_r = http_requests.post(f'{DISCORD_API}/oauth2/token', data={
        'client_id':     DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type':    'authorization_code',
        'code':          code,
        'redirect_uri':  DISCORD_REDIRECT_URI,
    }, headers={'Content-Type': 'application/x-www-form-urlencoded'})

    if token_r.status_code != 200:
        return ACCESS_DENIED.replace('{{message}}', 'Erreur d\'authentification Discord.')

    token_data   = token_r.json()
    access_token = token_data.get('access_token')

    user, roles = get_user_roles(access_token)
    if not user:
        return ACCESS_DENIED.replace('{{message}}', 'Impossible de recuperer tes informations Discord.')

    # Verifier que l'utilisateur est dans le serveur
    if not roles and roles != []:
        return ACCESS_DENIED.replace('{{message}}',
            'Tu n\'es pas membre du serveur TradePilot. Rejoins-le d\'abord : discord.gg/PRrADDxCM8')

    # Verifier qu'il a au moins un role produit
    user_role_ids = [str(r) for r in roles]
    has_access = any(rid in user_role_ids for rid in ROLES.values())

    if not has_access:
        return ACCESS_DENIED.replace('{{message}}',
            'Tu n\'as pas encore d\'offre active. Achete une offre sur tradepilotautomatisation.netlify.app')

    # Sauvegarder la session
    session['user_id']       = user['id']
    session['username']      = user['username']
    session['discriminator'] = user.get('discriminator', '0')
    session['roles']         = user_role_ids

    return redirect('/guide/dashboard')

@app.route('/guide/dashboard')
@login_required
def guide_dashboard():
    username  = session.get('username', 'Utilisateur')
    user_roles = session.get('roles', [])

    cards = ''
    if ROLES['licence'] in user_roles:
        cards += '''<a href="/guide/licence" class="card">
          <div class="card-icon">🔑</div>
          <div class="card-title">Guide Licence</div>
          <div class="card-desc">Installation complete — VPS AWS, MT4/MT5, EA, Script Python, NSSM</div>
        </a>'''
    else:
        cards += '''<div class="card locked">
          <div class="card-icon">🔑</div>
          <div class="card-title">Guide Licence</div>
          <div class="card-desc">Non disponible avec ton offre actuelle.</div>
          <div class="locked-label">ACCES NON INCLUS</div>
        </div>'''

    if ROLES['setup'] in user_roles:
        cards += '''<a href="/guide/setup" class="card">
          <div class="card-icon">⚙️</div>
          <div class="card-title">Guide Setup Pro</div>
          <div class="card-desc">Ce qui est installe, comment preparer la session TeamViewer</div>
        </a>'''

    if ROLES['signal'] in user_roles:
        cards += '''<a href="/guide/signal" class="card">
          <div class="card-icon">📡</div>
          <div class="card-title">Guide Signal VIP</div>
          <div class="card-desc">Lire les signaux, gestion du risque, copier sur MT4/MT5</div>
        </a>'''

    return DASHBOARD.replace('{{username}}', username).replace('{{cards}}', cards)

@app.route('/guide/licence')
@login_required
def guide_licence():
    user_roles = session.get('roles', [])
    if ROLES['licence'] not in user_roles:
        return ACCESS_DENIED.replace('{{message}}', 'Ce guide necessite la Licence TradePilot.')
    username = session.get('username', 'Utilisateur')
    return GUIDE_TEMPLATE\
        .replace('{{title}}', 'Guide Licence')\
        .replace('{{username}}', username)\
        .replace('{{guide_css}}', get_guide_css())\
        .replace('{{guide_content}}', LICENCE_CONTENT)

@app.route('/guide/setup')
@login_required
def guide_setup():
    user_roles = session.get('roles', [])
    if ROLES['setup'] not in user_roles:
        return ACCESS_DENIED.replace('{{message}}', 'Ce guide necessite le Setup Pro.')
    username = session.get('username', 'Utilisateur')
    return GUIDE_TEMPLATE\
        .replace('{{title}}', 'Guide Setup Pro')\
        .replace('{{username}}', username)\
        .replace('{{guide_css}}', get_guide_css())\
        .replace('{{guide_content}}', SETUP_CONTENT)

@app.route('/guide/signal')
@login_required
def guide_signal():
    user_roles = session.get('roles', [])
    if ROLES['signal'] not in user_roles:
        return ACCESS_DENIED.replace('{{message}}', 'Ce guide necessite le Signal VIP.')
    username = session.get('username', 'Utilisateur')
    return GUIDE_TEMPLATE\
        .replace('{{title}}', 'Guide Signal VIP')\
        .replace('{{username}}', username)\
        .replace('{{guide_css}}', get_guide_css())\
        .replace('{{guide_content}}', SIGNAL_CONTENT)

@app.route('/guide/logout')
def guide_logout():
    session.clear()
    return redirect('/guide/login')



@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "TradePilot Bot actif ✅"}), 200

@app.route("/achat", methods=["POST"])
def achat():
    data = request.json or {}
    discord_id = data.get("discord_id")
    product    = data.get("product")
    email      = data.get("email", "—")
    amount     = data.get("amount", "—")
    name       = data.get("name", "—")
    if not discord_id or not product:
        return jsonify({"error": "discord_id et product requis"}), 400
    asyncio.run_coroutine_threadsafe(
        handle_purchase(int(discord_id), product, email, amount, name), bot.loop
    )
    return jsonify({"status": "ok"}), 200


# ════════════════════════════════════════════════════════
#  EVENTS
# ════════════════════════════════════════════════════════
@bot.event
async def on_ready():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  ✅ TradePilot Bot connecté")
    print(f"  👤 {bot.user}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    await asyncio.sleep(8)

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f"❌ Serveur {GUILD_ID} introuvable — retry dans 5s")
        print(f"Serveurs disponibles : {[g.id for g in bot.guilds]}")
        await asyncio.sleep(5)
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Serveur toujours introuvable")
            return

    print("Salons :")
    for ch in guild.text_channels:
        print(f"  - [{ch.id}] {ch.name}")

    # Envoyer les boutons dans les salons
    configs = [
        (CH_TICKET, "🎫 Support TradePilot",
         "**Tu as acheté une offre ?**\n→ Clique et envoie ta confirmation Stripe\n\n"
         "**Tu as une question ?**\n→ Clique et pose ta question\n\nNous répondons dans la journée ✅",
         TicketView("general", "Support")),
        (CH_LIC, "🔑 Support Licence",
         "Un problème avec ton installation ?\nClique pour ouvrir un ticket.\n\nNous répondons dans la journée ✅",
         SupportLicView()),
        (CH_SETUP, "⚙️ Support Setup Pro",
         "Un problème avec ton Setup Pro ?\nClique pour ouvrir un ticket.\n\nNous répondons dans la journée ✅",
         SupportSetupView()),
        (CH_VIP, "💎 Support Signal VIP",
         "Un problème avec tes signaux ?\nClique pour ouvrir un ticket.\n\nNous répondons dans la journée ✅",
         SupportVipView()),
    ]

    for ch_id, title, desc, view in configs:
        ch = guild.get_channel(ch_id)
        if not ch:
            print(f"❌ Salon {ch_id} introuvable")
            continue
        # Vérifie si le bouton existe déjà
        found = False
        async for msg in ch.history(limit=20):
            if msg.author == bot.user and msg.components:
                found = True
                break
        if not found:
            embed = discord.Embed(title=title, description=desc, color=0xF5B830)
            embed.set_footer(text="TradePilot — Automatisation MT4 & MT5")
            await ch.send(embed=embed, view=view)
            print(f"✅ Bouton envoyé dans #{ch.name}")
        else:
            print(f"ℹ️ Bouton déjà présent dans #{ch.name}")


@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return

    # Rôle Membre
    role = member.guild.get_role(ROLE_MEMBRE)
    if role:
        try:
            await member.add_roles(role)
            print(f"✅ Rôle Membre → {member.display_name}")
        except Exception as e:
            print(f"❌ Erreur rôle : {e}")

    # Ajouter dans la liste de relance 48h
    data = load_relance()
    data[str(member.id)] = datetime.now().isoformat()
    save_relance(data)

    # DM de bienvenue
    try:
        embed = discord.Embed(
            title="👋 Bienvenue sur TradePilot !",
            description=(
                f"Salut **{member.display_name}** !\n\n"
                "TradePilot automatise tes signaux Telegram → MT4 & MT5.\n\n"
                "**Pour commencer :**\n"
                "→ Lis **#règles-et-infos** pour voir nos offres\n"
                "→ Consulte **#guide-débutant** si tu débutes\n"
                "→ Pose tes questions dans **#général-trading**\n\n"
                "À tout de suite ! ⚡"
            ),
            color=0xF5B830
        )
        embed.set_footer(text="TradePilot — Automatisation MT4 & MT5")
        await member.send(embed=embed)
        dm_status = "✅ DM envoyé"
    except discord.Forbidden:
        dm_status = "❌ DMs fermés"

    # Message dans salon arrivants
    arrivants = member.guild.get_channel(ARRIVANTS_CH)
    if arrivants:
        embed_arr = discord.Embed(
            title="👋 Bienvenue sur TradePilot !",
            description=(
                f"**{member.display_name}** vient de rejoindre ! 🎉\n\n"
                f"Tu es le **{member.guild.member_count}ème membre** 🚀\n\n"
                "→ Lis **#règles-et-infos**\n"
                "→ Questions dans **#général-trading**"
            ),
            color=0xF5B830
        )
        embed_arr.set_thumbnail(url=member.display_avatar.url)
        embed_arr.set_footer(text="TradePilot — Automatisation MT4 & MT5")
        await arrivants.send(embed=embed_arr)

    # Notif admin dans ventes-dashboard
    ventes = member.guild.get_channel(VENTES_CH)
    if ventes:
        embed_v = discord.Embed(title="👤 NOUVEAU MEMBRE", color=0x3498DB)
        embed_v.add_field(name="Membre",  value=f"{member.mention} ({member.display_name})", inline=True)
        embed_v.add_field(name="DM",      value=dm_status,                                   inline=True)
        embed_v.add_field(name="Total",   value=f"{member.guild.member_count} membres",      inline=True)
        embed_v.add_field(name="Compte",  value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed_v.set_footer(text="TradePilot — Automatisation MT4 & MT5")
        await ventes.send(embed=embed_v)


# ════════════════════════════════════════════════════════
#  GESTION ACHAT
# ════════════════════════════════════════════════════════
# ── BOT DE RELANCE 48H ───────────────────────────────────
import json
from discord.ext import tasks
from datetime import datetime, timedelta

RELANCE_FILE = "relance_data.json"
ROLE_PRODUITS = list(ROLES.values())

def load_relance():
    try:
        with open(RELANCE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_relance(data):
    with open(RELANCE_FILE, 'w') as f:
        json.dump(data, f)

@tasks.loop(minutes=30)
async def check_relance():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    data = load_relance()
    now = datetime.now()
    to_remove = []

    for user_id_str, join_time_str in data.items():
        try:
            join_time = datetime.fromisoformat(join_time_str)
            if now - join_time < timedelta(hours=48):
                continue

            member = guild.get_member(int(user_id_str))
            if not member:
                to_remove.append(user_id_str)
                continue

            member_role_ids = [r.id for r in member.roles]
            has_product = any(rid in member_role_ids for rid in ROLE_PRODUITS)

            if has_product:
                to_remove.append(user_id_str)
                continue

            try:
                embed = discord.Embed(
                    title="⚡ Tu as oublié quelque chose ?",
                    description=(
                        f"Salut **{member.display_name}** !\n\n"
                        "Tu as rejoint TradePilot il y a 2 jours mais tu n'as pas encore "
                        "automatise ton trading.\n\n"
                        "**On te fait une offre de lancement :**\n"
                        "Utilise le code **LAUNCH10** pour obtenir **-45%** sur toutes nos offres.\n\n"
                        "🔑 Licence : ~~99€~~ → **54€**\n"
                        "⚙️ Setup Pro : ~~200€~~ → **110€**\n"
                        "📡 Signal VIP : ~~59.99€~~ → **32.99€/mois**\n\n"
                        "→ tradepilotautomatisation.netlify.app\n\n"
                        "⚠️ Code limité aux 10 premiers — dépêche-toi !"
                    ),
                    color=0xF5B830
                )
                embed.set_footer(text="TradePilot — Automatisation MT4 & MT5")
                await member.send(embed=embed)
                print(f"✅ DM relance envoyé → {member.display_name}")
            except discord.Forbidden:
                print(f"⚠️ DMs fermés — {member.display_name}")

            to_remove.append(user_id_str)

        except Exception as e:
            print(f"❌ Erreur relance: {e}")
            to_remove.append(user_id_str)

    for uid in to_remove:
        data.pop(uid, None)
    save_relance(data)


async def handle_purchase(discord_id, product, email, amount, name):
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    try:
        member = guild.get_member(discord_id) or await guild.fetch_member(discord_id)
    except discord.NotFound:
        print(f"❌ Membre {discord_id} introuvable")
        return

    label = PRODUCT_LABELS.get(product, product)

    # Rôle
    role_id = ROLES.get(product)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            await member.add_roles(role)

    # Ticket
    msg_text = TICKET_MESSAGES["achat"].get(product, TICKET_MESSAGES["general"])
    ticket, already = await create_ticket(guild, member, "achat", f"🎫 {label}", msg_text, label)

    # DM
    try:
        embed_dm = discord.Embed(
            title="🎉 Ton achat est confirmé !",
            description=(
                f"Bonjour **{member.display_name}** !\n\n"
                f"Ton accès **{label}** est actif.\n\n"
                f"Ton ticket : {ticket.mention}\n"
                "Rends-toi dessus pour les prochaines étapes ✅"
            ),
            color=0xF5B830
        )
        await member.send(embed=embed_dm)
    except discord.Forbidden:
        pass

    # Notif ventes
    ventes = guild.get_channel(VENTES_CH)
    if ventes:
        embed_v = discord.Embed(title="💰 NOUVEL ACHAT", color=0x2ECC71)
        embed_v.add_field(name="Client",  value=f"{member.mention} ({name})", inline=True)
        embed_v.add_field(name="Produit", value=label,                        inline=True)
        embed_v.add_field(name="Email",   value=email,                        inline=True)
        embed_v.add_field(name="Montant", value=f"{amount}€",                 inline=True)
        embed_v.add_field(name="Ticket",  value=ticket.mention,               inline=True)
        embed_v.add_field(name="Statut",  value="✅ Rôle · ✅ Ticket · ✅ DM", inline=False)
        await ventes.send(content=f"<@&{ROLE_ADMIN}>", embed=embed_v)

    print(f"✅ Achat traité : {member.display_name} — {label}")


# ════════════════════════════════════════════════════════
#  LANCEMENT
# ════════════════════════════════════════════════════════
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    bot.run(BOT_TOKEN)
