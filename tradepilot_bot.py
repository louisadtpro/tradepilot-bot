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
BOT_TOKEN        = os.environ.get("BOT_TOKEN", "COLLE_TON_TOKEN_ICI")
GUILD_ID         = 1518723776823558184
VENTES_CHANNEL   = 1519256169338638346
TICKET_CHANNEL   = None  # ID du salon #ouvrir-un-ticket (auto-détecté)
ROLE_MEMBRE      = 1519010089032486933

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
        "→ Quelle est ta question ou ton problème ?\n"
        "→ Quelle offre as-tu achetée ?\n\n"
        "Nous répondons en général dans la journée ✅"
    ),
}

intents = discord.Intents.all()
app     = Flask(__name__)


# ════════════════════════════════════════════════════════
#  BOUTON TICKET MANUEL
# ════════════════════════════════════════════════════════
class TicketButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Ouvrir un ticket",
        style=discord.ButtonStyle.primary,
        custom_id="open_ticket"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild  = interaction.guild
        member = interaction.user

        # Vérifie si un ticket existe déjà pour ce membre
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

        # Crée la catégorie si elle n'existe pas
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
            topic=f"Support — {member.display_name}"
        )

        # Message dans le ticket
        embed = discord.Embed(
            title=f"🎫 Ticket de {member.display_name}",
            description=FIRST_MESSAGES["support"],
            color=0xF5B830
        )
        embed.set_footer(text="TradePilot — Automatisation MT4 & MT5")

        # Bouton pour fermer le ticket
        close_view = CloseTicketButton()
        await ticket.send(content=member.mention, embed=embed, view=close_view)

        await interaction.response.send_message(
            f"✅ Ton ticket a été créé : {ticket.mention}",
            ephemeral=True
        )


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
#  BOT
# ════════════════════════════════════════════════════════
class TradePilotBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(TicketButton())
        self.add_view(CloseTicketButton())


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


# ── MEMBRE REJOINT → rôle Membre + DM ───────────────────
@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return

    role = member.guild.get_role(ROLE_MEMBRE)
    if role:
        await member.add_roles(role)
        print(f"✅ Rôle Membre → {member.display_name}")

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
        print(f"⚠️ DMs fermés — {member.display_name}")


# ── GESTION D'UN ACHAT ───────────────────────────────────
async def handle_purchase(discord_id, product, email, amount, name):
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Serveur introuvable")
        return

    try:
        member = guild.get_member(discord_id) or await guild.fetch_member(discord_id)
    except discord.NotFound:
        print(f"❌ Membre {discord_id} introuvable")
        return

    label = PRODUCT_LABELS.get(product, product)

    # 1. Donner le rôle
    role = guild.get_role(ROLES.get(product))
    if role:
        await member.add_roles(role)
        print(f"✅ Rôle {role.name} → {member.display_name}")

    # 2. Créer le ticket
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

    # 3. Message dans le ticket
    embed_t = discord.Embed(
        title=f"🎫 Ticket de {member.display_name}",
        description=FIRST_MESSAGES.get(product, "Bienvenue !"),
        color=0xF5B830
    )
    embed_t.add_field(name="Produit", value=label,  inline=True)
    embed_t.add_field(name="Email",   value=email,  inline=True)
    embed_t.set_footer(text="TradePilot — Automatisation MT4 & MT5")

    close_view = CloseTicketButton()
    await ticket.send(content=member.mention, embed=embed_t, view=close_view)

    # 4. DM au client
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
        await ticket.send("⚠️ DMs désactivés — contacte le client manuellement.")

    # 5. Notification ventes-dashboard
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

    print(f"✅ Achat traité : {member.display_name} — {label}")


# ── DÉMARRAGE → envoie le bouton dans #ouvrir-un-ticket ─
@bot.event
async def on_ready():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  ✅ TradePilot Bot connecté")
    print(f"  👤 {bot.user}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    # Cherche le salon #ouvrir-un-ticket
    ticket_channel = discord.utils.get(guild.text_channels, name="ouvrir-un-ticket")
    if ticket_channel:
        # Vérifie si le message bouton existe déjà
        async for msg in ticket_channel.history(limit=10):
            if msg.author == bot.user:
                return  # Déjà envoyé

        embed = discord.Embed(
            title="🎫 Support TradePilot",
            description=(
                "**Tu as acheté une offre ?**\n"
                "→ Clique sur le bouton et envoie ta confirmation Stripe\n\n"
                "**Tu as une question avant d'acheter ?**\n"
                "→ Clique et pose ta question directement\n\n"
                "Notre équipe répond dans la journée ✅"
            ),
            color=0xF5B830
        )
        embed.set_footer(text="TradePilot — Automatisation MT4 & MT5")
        await ticket_channel.send(embed=embed, view=TicketButton())
        print("✅ Bouton ticket envoyé dans #ouvrir-un-ticket")


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    bot.run(BOT_TOKEN)
