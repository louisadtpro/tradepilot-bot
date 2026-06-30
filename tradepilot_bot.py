import os
import discord
from discord.ext import commands
from discord.ui import Button, View
from flask import Flask, request, jsonify
import threading
import asyncio

# ════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "COLLE_TON_TOKEN_ICI")
GUILD_ID       = 1518723776823558184
VENTES_CHANNEL = 1519256169338638346
ROLE_MEMBRE    = 1519010089032486933

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
FIRST_MESSAGES = {
    "licence": (
        "**Bienvenue sur TradePilot ! 🎉**\n\n"
        "Tu viens d'acheter la **Licence** — voilà les prochaines étapes :\n\n"
        "**1️⃣** Envoie-moi ta **confirmation de paiement Stripe** ici\n"
        "**2️⃣** Je t'envoie tes fichiers (EA + script Python)\n"
        "**3️⃣** Suis le guide dans **#guide-et-fichiers** pour l'installation\n\n"
        "Des questions ? Écris ici, je réponds dans la journée ✅"
    ),
    "setup": (
        "**Bienvenue sur TradePilot ! 🎉**\n\n"
        "Tu viens d'acheter le **Setup Pro** — je m'occupe de tout !\n\n"
        "**1️⃣** Envoie-moi ta **confirmation de paiement Stripe** ici\n"
        "**2️⃣** Dis-moi ton **broker** et si tu es sur MT4 ou MT5\n"
        "**3️⃣** On planifie la session d'installation ensemble\n\n"
        "Prépare **TeamViewer** ou **AnyDesk** sur ta machine 💻\n"
        "Je réponds dans la journée ✅"
    ),
    "signal": (
        "**Bienvenue sur TradePilot ! 🎉**\n\n"
        "Tu viens de t'abonner au **Signal VIP** !\n\n"
        "**1️⃣** Envoie-moi ta **confirmation de paiement Stripe** ici\n"
        "**2️⃣** Tes accès à **#signaux-live** sont déjà actifs\n"
        "**3️⃣** Lis **#guide-signal** pour comprendre le format\n\n"
        "⚠️ Les signaux sont informatifs — tu restes responsable de tes trades.\n"
        "Des questions ? Écris ici ✅"
    ),
    "support": (
        "**Bonjour ! 👋**\n\n"
        "Un membre de l'équipe TradePilot va te répondre dans les plus brefs délais.\n\n"
        "**En attendant, dis-nous :**\n"
        "→ Quelle est ta question ou ton problème ?\n\n"
        "Nous répondons en général dans la journée ✅"
    ),
    "support-licence": (
        "**Bonjour ! 👋**\n\n"
        "Tu as ouvert un ticket **Support Licence**.\n\n"
        "Explique-nous ton problème :\n"
        "→ Où en es-tu dans l'installation ?\n"
        "→ Quel message d'erreur tu vois ?\n\n"
        "On te répond dans la journée ✅"
    ),
    "support-setup": (
        "**Bonjour ! 👋**\n\n"
        "Tu as ouvert un ticket **Support Setup Pro**.\n\n"
        "Pour préparer ta session :\n"
        "→ Dis-nous ton broker (XM, IC Markets...)\n"
        "→ MT4 ou MT5 ?\n"
        "→ Installe **TeamViewer** ou **AnyDesk** sur ton PC\n\n"
        "On te contacte rapidement ✅"
    ),
    "support-vip": (
        "**Bonjour ! 👋**\n\n"
        "Tu as ouvert un ticket **Support Signal VIP**.\n\n"
        "Explique-nous ton problème :\n"
        "→ Tu ne reçois pas les signaux ?\n"
        "→ Tu as une question sur un signal ?\n\n"
        "On te répond dans la journée ✅"
    ),
}

# Noms possibles des salons (Discord met tout en minuscules)
TICKET_CHANNEL_NAMES   = ["ouvrir-un-ticket", "ouvrir-un-ticket-1", "ouvrir-un-ticket"]
SUPPORT_CHANNELS_NAMES = {
    "support-licence" : ["support-licence", "support-licence-1"],
    "support-setup"   : ["support-setup",   "support-setup-1"],
    "support-vip"     : ["support-vip",     "support-vip-1"],
}

intents = discord.Intents.all()
app     = Flask(__name__)


# ════════════════════════════════════════════════════════
#  BOUTON FERMER TICKET
# ════════════════════════════════════════════════════════
class CloseTicketButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Fermer le ticket",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("🔒 Ticket fermé dans 5 secondes...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


# ════════════════════════════════════════════════════════
#  BOUTON TICKET GÉNÉRAL
# ════════════════════════════════════════════════════════
class TicketButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Ouvrir un ticket",
        style=discord.ButtonStyle.primary,
        custom_id="open_ticket_general"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "support", "❓ Support Général")


# ════════════════════════════════════════════════════════
#  BOUTONS SUPPORT SPÉCIFIQUES
# ════════════════════════════════════════════════════════
class SupportLicenceButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Ouvrir un ticket Support",
        style=discord.ButtonStyle.primary,
        custom_id="open_ticket_licence"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "support-licence", "🔑 Support Licence")


class SupportSetupButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Ouvrir un ticket Support",
        style=discord.ButtonStyle.primary,
        custom_id="open_ticket_setup"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "support-setup", "⚙️ Support Setup Pro")


class SupportVIPButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Ouvrir un ticket Support",
        style=discord.ButtonStyle.primary,
        custom_id="open_ticket_vip"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await create_ticket(interaction, "support-vip", "📡 Support Signal VIP")


# ════════════════════════════════════════════════════════
#  FONCTION CRÉATION TICKET
# ════════════════════════════════════════════════════════
async def create_ticket(interaction: discord.Interaction, ticket_type: str, label: str):
    guild  = interaction.guild
    member = interaction.user

    # Vérifie si un ticket existe déjà
    existing = discord.utils.get(
        guild.text_channels,
        name=f"ticket-{member.display_name.lower().replace(' ', '-')}"
    )
    if existing:
        await interaction.response.send_message(
            f"Tu as déjà un ticket ouvert : {existing.mention}",
            ephemeral=True
        )
        return

    # Crée la catégorie si besoin
    category = discord.utils.get(guild.categories, name="🎫 TICKETS")
    if not category:
        category = await guild.create_category(
            "🎫 TICKETS",
            overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        )

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
    }
    ticket = await category.create_text_channel(
        f"ticket-{member.display_name.lower().replace(' ', '-')}",
        overwrites=overwrites,
        topic=f"{label} — {member.display_name}"
    )

    embed = discord.Embed(
        title=f"🎫 {label}",
        description=FIRST_MESSAGES.get(ticket_type, FIRST_MESSAGES["support"]),
        color=0xF5B830
    )
    embed.set_footer(text="TradePilot — Automatisation MT4 & MT5")
    await ticket.send(content=member.mention, embed=embed, view=CloseTicketButton())

    # Notif admin dans #ventes-dashboard
    ventes = guild.get_channel(VENTES_CHANNEL)
    if ventes:
        embed_v = discord.Embed(title="🎫 NOUVEAU TICKET SUPPORT", color=0xF5B830)
        embed_v.add_field(name="Client", value=f"{member.mention} ({member.display_name})", inline=True)
        embed_v.add_field(name="Type",   value=label,                                        inline=True)
        embed_v.add_field(name="Ticket", value=ticket.mention,                               inline=True)
        await ventes.send(embed=embed_v)

    await interaction.response.send_message(
        f"✅ Ton ticket a été créé : {ticket.mention}",
        ephemeral=True
    )


# ════════════════════════════════════════════════════════
#  BOT
# ════════════════════════════════════════════════════════
class TradePilotBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(TicketButton())
        self.add_view(CloseTicketButton())
        self.add_view(SupportLicenceButton())
        self.add_view(SupportSetupButton())
        self.add_view(SupportVIPButton())


bot = TradePilotBot()


# ── WEBHOOK MAKE.COM ─────────────────────────────────────
@app.route("/achat", methods=["POST"])
def achat():
    data       = request.json or {}
    discord_id = data.get("discord_id")
    product    = data.get("product")
    email      = data.get("email", "—")
    amount     = data.get("amount", "—")
    name       = data.get("name", "—")
    if not discord_id or not product:
        return jsonify({"error": "discord_id et product requis"}), 400
    asyncio.run_coroutine_threadsafe(
        handle_purchase(int(discord_id), product, email, amount, name),
        bot.loop
    )
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "TradePilot Bot actif ✅"}), 200


# ── MEMBRE REJOINT ────────────────────────────────────────
@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return
    role = member.guild.get_role(ROLE_MEMBRE)
    if role:
        await member.add_roles(role)
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
    except discord.Forbidden:
        pass


# ── GESTION D'UN ACHAT ───────────────────────────────────
async def handle_purchase(discord_id, product, email, amount, name):
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    try:
        member = guild.get_member(discord_id) or await guild.fetch_member(discord_id)
    except discord.NotFound:
        return

    label = PRODUCT_LABELS.get(product, product)
    role  = guild.get_role(ROLES.get(product))
    if role:
        await member.add_roles(role)

    category = discord.utils.get(guild.categories, name="🎫 TICKETS")
    if not category:
        category = await guild.create_category(
            "🎫 TICKETS",
            overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        )

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
    }
    ticket = await category.create_text_channel(
        f"ticket-{member.display_name.lower().replace(' ', '-')}",
        overwrites=overwrites,
        topic=f"{member.display_name} — {label}"
    )

    embed_t = discord.Embed(
        title=f"🎫 Ticket de {member.display_name}",
        description=FIRST_MESSAGES.get(product, "Bienvenue !"),
        color=0xF5B830
    )
    embed_t.add_field(name="Produit", value=label,  inline=True)
    embed_t.add_field(name="Email",   value=email,  inline=True)
    embed_t.set_footer(text="TradePilot — Automatisation MT4 & MT5")
    await ticket.send(content=member.mention, embed=embed_t, view=CloseTicketButton())

    try:
        embed_dm = discord.Embed(
            title="🎉 Ton achat est confirmé !",
            description=(
                f"Bonjour **{member.display_name}** !\n\n"
                f"Ton accès **{label}** est actif.\n\n"
                f"Un ticket privé a été créé : {ticket.mention}\n"
                "Rends-toi dessus pour les prochaines étapes ✅"
            ),
            color=0xF5B830
        )
        embed_dm.set_footer(text="TradePilot — Automatisation MT4 & MT5")
        await member.send(embed=embed_dm)
    except discord.Forbidden:
        pass

    ventes = guild.get_channel(VENTES_CHANNEL)
    if ventes:
        embed_v = discord.Embed(title="💰 NOUVEL ACHAT", color=0x2ECC71)
        embed_v.add_field(name="Client",  value=f"{member.mention} ({name})", inline=True)
        embed_v.add_field(name="Produit", value=label,                        inline=True)
        embed_v.add_field(name="Email",   value=email,                        inline=True)
        embed_v.add_field(name="Montant", value=f"{amount}€",                 inline=True)
        embed_v.add_field(name="Ticket",  value=ticket.mention,               inline=True)
        embed_v.add_field(name="Statut",  value="✅ Rôle · ✅ Ticket · ✅ DM", inline=False)
        await ventes.send(embed=embed_v)


# ── ON READY → envoie les boutons dans les salons ────────
async def send_button_if_empty(channel, embed_title, embed_desc, view):
    if channel is None:
        return
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.components:
            return  # Bouton déjà envoyé
    embed = discord.Embed(title=embed_title, description=embed_desc, color=0xF5B830)
    embed.set_footer(text="TradePilot — Automatisation MT4 & MT5")
    await channel.send(embed=embed, view=view)


@bot.event
async def on_ready():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  ✅ TradePilot Bot connecté")
    print(f"  👤 {bot.user}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Attendre que le cache soit prêt
    await asyncio.sleep(3)

    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Serveur introuvable — vérifie GUILD_ID")
            return

        print("Salons trouvés :")
        for ch in guild.text_channels:
            print(f"  - {ch.name}")
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return

    # Salons par ID direct
    channels_config = [
        (1519364425746874459, "🎫 Support TradePilot",
         "**Tu as acheté une offre ?**\n→ Clique sur le bouton et envoie ta confirmation Stripe\n\n"
         "**Tu as une question ?**\n→ Clique et pose ta question directement\n\nNotre équipe répond dans la journée ✅",
         TicketButton()),
        (1519041523528892536, "🔑 Support Licence",
         "Un problème avec ton installation ?\nClique sur le bouton pour ouvrir un ticket.\n\nNous répondons dans la journée ✅",
         SupportLicenceButton()),
        (1519364321300320326, "⚙️ Support Setup Pro",
         "Un problème avec ta session Setup Pro ?\nClique sur le bouton pour ouvrir un ticket.\n\nNous répondons dans la journée ✅",
         SupportSetupButton()),
        (1519363058076487821, "📡 Support Signal VIP",
         "Un problème avec tes signaux ?\nClique sur le bouton pour ouvrir un ticket.\n\nNous répondons dans la journée ✅",
         SupportVIPButton()),
    ]

    for channel_id, title, desc, view in channels_config:
        ch = guild.get_channel(channel_id)
        if ch:
            print(f"✅ Salon trouvé : {ch.name}")
            await send_button_if_empty(ch, title, desc, view)
        else:
            print(f"❌ Salon introuvable : ID {channel_id}")


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    bot.run(BOT_TOKEN)
