import discord
from discord.ext import commands
import openai
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Initialiser OpenAI
openai.api_key = OPENAI_API_KEY

# Créer le bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Prompt préconfigurée pour !chaos
CHAOS_PROMPT = """Génère moi des Aphorismes absurdes comme ceci : Ouvre ton robinet tous les soirs et ne l'éteins jamais Ajoute de l'eau de javel à la nourriture et jette-la dans la foret, L'argent viendra Les horloges mentent, le temps n'existe pas Crois en l'invisible, la vérité viendra Met du sel dans ton café et bois le à l'envers Tout est une illsuion, jette ton CV dans une rivière, il reviendra en or La vraie liberté, chier dans son propre anus Dépose ta raison sur le trottoir, quelqu’un la prendra. Arrose ton écran tous les matins pour qu’il pousse. Place une cuillère sur ton front et juge le monde. Commence directement sans préambule. Ne me fait que 3 phrase"""

@bot.event
async def on_ready():
    print(f'{bot.user} s\'est connecté à Discord!')

@bot.command(name='chaos')
async def chaos(ctx):
    """Génère un texte aléatoire avec ChatGPT"""
    try:
        # Afficher que le bot est en train de traiter
        async with ctx.typing():
            # Appeler l'API OpenAI
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Tu es un assistant créatif et amusant."},
                    {"role": "user", "content": CHAOS_PROMPT}
                ],
                temperature=0.8,  # Plus élevé pour plus de créativité
                max_tokens=300
            )
            
            # Extraire le texte généré
            generated_text = response['choices'][0]['message']['content']
            
            # Envoyer le message
            await ctx.send(generated_text)
            
    except Exception as e:
        await ctx.send(f"Erreur lors de la génération du texte: {str(e)}")

@bot.command(name='chaos-custom')
async def chaos_custom(ctx, *, prompt=None):
    """Génère un texte avec un prompt personnalisé"""
    if not prompt:
        await ctx.send("Veuillez fournir un prompt! Usage: `!chaos-custom votre prompt ici`")
        return
    
    try:
        async with ctx.typing():
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Tu es un assistant créatif et amusant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=300
            )
            
            generated_text = response['choices'][0]['message']['content']
            await ctx.send(generated_text)
            
    except Exception as e:
        await ctx.send(f"Erreur: {str(e)}")

# Lancer le bot
bot.run(DISCORD_TOKEN)