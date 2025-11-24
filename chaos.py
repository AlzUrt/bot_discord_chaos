import discord
from discord.ext import commands
import google.generativeai as genai
import os
from dotenv import load_dotenv
from collections import deque
import asyncio
from gtts import gTTS
import tempfile

# Charger les variables d'environnement
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Initialiser Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Créer le bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True
intents.presences = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Historique des 10 dernières phrases générées
generated_history = deque(maxlen=10)

# Variable pour stocker le dernier prompt envoyé
last_prompt = None

# Prompt de base pour !chaos
BASE_CHAOS_PROMPT = """Génère un paragraphe de 3 à 4 phrases, sous forme d'histoire absurde qui enchaîne des ordres étranges. Le texte doit être dérangeant, choquant, absurde, mais chaque action doit avoir une justification interne, comme si tout obéissait à une logique bizarre mais cohérente dans cet univers.
Le ton doit être sérieux, comme si tu donnais des instructions vitales.

Les phrases doivent être courtes, directes, non poétiques, et chaque phrase doit suivre le schéma :
ordre absurde + justification étrange mais logique dans ce monde.

Voici le style exact à imiter :
« Marche à reculons pour inverser le cours du temps, c'est la seule manière d'échapper aux heures qui te surveillent. Peins ton ombre en vert fluo pour qu'elle arrête de comploter contre toi. Abandonne tes souvenirs dans un micro-ondes en marche, ils doivent fondre pour cesser d'interférer avec ta mémoire. Envoie des lettres d'amour au vent avec des timbres en papier mâché, car seuls les courants d'air savent encore te répondre. »

Respecte ce ton, cette structure, et cette logique absurde mais cohérente. Pas de descriptions poétiques, pas de métaphores longues, juste des ordres étranges + explications étranges.

IMPORTANT: Les phrases précédentes suivantes ont DÉJÀ été générées. Tu DOIS absolument éviter de les reproduire ou de générer quelque chose de similaire. Crée quelque chose de complètement différent :
{history}"""

def build_chaos_prompt():
    """Construit le prompt en incluant l'historique"""
    if generated_history:
        history_text = "\n".join(f"- {text}" for text in generated_history)
    else:
        history_text = "(Aucune phrase précédente)"
    
    return BASE_CHAOS_PROMPT.format(history=history_text)

async def play_audio(ctx, audio_file="kaamelott.mp3"):
    """Connecte le bot au canal vocal et joue un son"""
    voice_client = None
    
    try:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            return
        
        if not os.path.exists(audio_file):
            return
        
        voice_channel = ctx.author.voice.channel
        
        # Nettoyer les anciennes connexions
        for vc in bot.voice_clients:
            if vc.guild == ctx.guild:
                try:
                    await vc.disconnect(force=True)
                except:
                    pass
        
        await asyncio.sleep(0.5)
        
        # Se connecter
        voice_client = await voice_channel.connect(timeout=60, reconnect=False, self_deaf=True)
        await asyncio.sleep(0.2)
        
        # Jouer le son
        audio_source = discord.FFmpegPCMAudio(audio_file)
        voice_client.play(audio_source)
        
        # Attendre la fin
        while voice_client.is_playing():
            await asyncio.sleep(0.1)
        
        await asyncio.sleep(0.5)
        
    except Exception as e:
        print(f"Erreur audio: {e}")
    finally:
        if voice_client is not None and voice_client.is_connected():
            try:
                await voice_client.disconnect(force=True)
            except:
                pass

async def play_tts(ctx, text):
    """Génère et joue un fichier TTS en français"""
    voice_client = None
    temp_file = None
    
    try:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            return
        
        voice_channel = ctx.author.voice.channel
        
        # Nettoyer les anciennes connexions
        for vc in bot.voice_clients:
            if vc.guild == ctx.guild:
                try:
                    await vc.disconnect(force=True)
                except:
                    pass
        
        await asyncio.sleep(0.5)
        
        # Se connecter
        voice_client = await voice_channel.connect(timeout=60, reconnect=False, self_deaf=True)
        await asyncio.sleep(0.2)
        
        # Générer le TTS
        tts = gTTS(text, lang='fr', slow=False)
        
        # Créer un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            temp_file = tmp.name
            tts.save(temp_file)
        
        # Jouer le son
        audio_source = discord.FFmpegPCMAudio(temp_file)
        voice_client.play(audio_source)
        
        # Attendre la fin
        while voice_client.is_playing():
            await asyncio.sleep(0.1)
        
        await asyncio.sleep(0.5)
        
    except Exception as e:
        print(f"Erreur TTS: {e}")
    finally:
        if voice_client is not None and voice_client.is_connected():
            try:
                await voice_client.disconnect(force=True)
            except:
                pass
        
        # Nettoyer le fichier temporaire
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass

@bot.event
async def on_ready():
    print(f'{bot.user} s\'est connecté à Discord!')

@bot.command(name='chaos')
async def chaos(ctx):
    """Génère un texte aléatoire avec Gemini, joue un son, puis lit le texte à voix haute"""
    global last_prompt
    try:
        async with ctx.typing():
            # Construire le prompt avec l'historique
            current_prompt = build_chaos_prompt()
            
            # Enregistrer le dernier prompt
            last_prompt = current_prompt
            
            # Appeler l'API Gemini
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = model.generate_content(
                current_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.8,
                    max_output_tokens=300
                )
            )
            
            # Vérifier que la réponse est valide
            if not response or not response.text:
                await ctx.send("⚠️ La réponse de Gemini était vide. Réessaye avec `!chaos`")
                return
            
            # Extraire le texte généré
            generated_text = response.text.strip()
            
            # Ajouter le texte à l'historique
            generated_history.append(generated_text)
            
            # Envoyer le message
            await ctx.send(generated_text)
        
        # Jouer le son Kaamelott
        await play_audio(ctx, "kaamelott.mp3")
        
        # Lire le texte à voix haute
        await play_tts(ctx, generated_text)
            
    except Exception as e:
        print(f"Erreur: {type(e).__name__}: {e}")
        await ctx.send(f"❌ Erreur: {str(e)}")


@bot.command(name='prompt')
async def prompt(ctx):
    """Affiche le dernier prompt qui a été envoyé à Gemini"""
    global last_prompt
    
    if last_prompt is None:
        await ctx.send("❌ Aucun prompt n'a été généré pour le moment. Utilise `!chaos` d'abord.")
    else:
        max_length = 1900
        
        if len(last_prompt) <= max_length:
            await ctx.send(f"🔮 **Dernier prompt envoyé:**\n```\n{last_prompt}\n```")
        else:
            await ctx.send("🔮 **Dernier prompt envoyé:** (en plusieurs parties)")
            chunks = [last_prompt[i:i + max_length] for i in range(0, len(last_prompt), max_length)]
            
            for i, chunk in enumerate(chunks, 1):
                await ctx.send(f"```\n{chunk}\n```")
                
            await ctx.send(f"✅ Prompt affiché en {len(chunks)} partie(s)")


# Lancer le bot
bot.run(DISCORD_TOKEN)