import os
import time
import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View
from flask import Flask, request, jsonify
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


# ════════════════════════════════════════════════════════
#  FLASK
# ════════════════════════════════════════════════════════
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
    await asyncio.sleep(3)

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Serveur introuvable")
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
