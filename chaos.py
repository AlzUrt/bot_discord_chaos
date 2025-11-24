import discord
from discord.ext import commands
import google.generativeai as genai
import os
from dotenv import load_dotenv
from collections import deque
import asyncio
from elevenlabs.client import ElevenLabs
import tempfile

# Charger les variables d'environnement
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

# Initialiser Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Initialiser ElevenLabs
client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

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

# ===== CONFIGURATION TTS =====
# Voix disponibles: https://elevenlabs.io/docs/voices
TTS_VOICE_ID = "4TfTGcPwoefWe878B0rm"  # Voice ID de la voix sélectionnée
TTS_STABILITY = 0.5  # 0.0-1.0 (plus bas = plus de variation)
TTS_SIMILARITY = 0.75  # 0.0-1.0 (plus haut = plus proche de la voix)
TTS_SPEED = 1.0  # Vitesse de lecture (0.5-2.0)

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
    """Génère et joue un fichier TTS avec ElevenLabs"""
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
        
        # Générer le TTS avec ElevenLabs
        print(f"Génération TTS avec ElevenLabs...")
        audio = client.text_to_speech.convert(
            text=text,
            voice_id=TTS_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        
        # Sauvegarder dans un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            temp_file = tmp.name
            for chunk in audio:
                tmp.write(chunk)
        
        print(f"TTS généré, lecture en cours...")
        
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


@bot.command(name='voices')
async def voices(ctx):
    """Affiche les voix disponibles"""
    try:
        voices = client.voices.get_all()
        
        response = "🎤 **Voix disponibles ElevenLabs:**\n\n"
        for voice in voices:
            response += f"`{voice.voice_id}` - {voice.name}\n"
        
        response += f"\n**Voix actuelle:** `{TTS_VOICE_ID}`\n"
        response += f"\nUtilisez `!setvoice <voice_id>` pour changer"
        
        # Envoyer en plusieurs messages si trop long
        if len(response) > 2000:
            parts = [response[i:i+2000] for i in range(0, len(response), 2000)]
            for part in parts:
                await ctx.send(part)
        else:
            await ctx.send(response)
            
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")


@bot.command(name='setvoice')
async def setvoice(ctx, voice_id: str):
    """Change la voix TTS ElevenLabs"""
    global TTS_VOICE_ID
    
    try:
        # Vérifier que la voix existe
        voices = client.voices.get_all()
        voice_ids = [v.voice_id for v in voices]
        
        if voice_id in voice_ids:
            TTS_VOICE_ID = voice_id
            # Trouver le nom de la voix
            voice_name = next((v.name for v in voices if v.voice_id == voice_id), voice_id)
            await ctx.send(f"✅ Voix changée à: **{voice_name}** (`{voice_id}`)")
        else:
            await ctx.send(f"❌ Voix invalide. Utilisez `!voices` pour voir les options.")
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")


@bot.command(name='setstability')
async def setstability(ctx, stability: float):
    """Change la stabilité de la voix (0.0-1.0)
    Plus bas = plus de variation naturelle
    Plus haut = plus de stabilité
    """
    global TTS_STABILITY
    
    if 0.0 <= stability <= 1.0:
        TTS_STABILITY = stability
        await ctx.send(f"✅ Stabilité changée à: `{stability}`")
    else:
        await ctx.send(f"❌ La stabilité doit être entre 0.0 et 1.0")


@bot.command(name='setsimilarity')
async def setsimilarity(ctx, similarity: float):
    """Change la similarité de la voix (0.0-1.0)
    Plus bas = différent de la voix de base
    Plus haut = plus proche de la voix de base
    """
    global TTS_SIMILARITY
    
    if 0.0 <= similarity <= 1.0:
        TTS_SIMILARITY = similarity
        await ctx.send(f"✅ Similarité changée à: `{similarity}`")
    else:
        await ctx.send(f"❌ La similarité doit être entre 0.0 et 1.0")


@bot.command(name='ttsstatus')
async def ttsstatus(ctx):
    """Affiche les paramètres TTS actuels"""
    try:
        voices = client.voices.get_all()
        voice_name = next((v.name for v in voices if v.voice_id == TTS_VOICE_ID), "Inconnue")
        
        response = f"""
🎤 **Paramètres TTS ElevenLabs:**
• Voix: **{voice_name}** (`{TTS_VOICE_ID}`)
• Stabilité: `{TTS_STABILITY}` (0=variation, 1=stable)
• Similarité: `{TTS_SIMILARITY}` (0=différent, 1=identique)
• Modèle: `eleven_multilingual_v2`

📝 **Commandes TTS disponibles:**
`!voices` - Voir les voix disponibles
`!setvoice <id>` - Changer la voix
`!setstability <0.0-1.0>` - Changer la stabilité
`!setsimilarity <0.0-1.0>` - Changer la similarité
`!ttsstatus` - Afficher ces paramètres
"""
        await ctx.send(response)
    except Exception as e:
        await ctx.send(f"❌ Erreur: {e}")


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