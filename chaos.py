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
TTS_SPEED = 1.0  # Vitesse de lecture (0.5 à 2.0, défaut 1.0)

# Dictionnaire des voix prédéfinies (exemple)
VOICES_PRESETS = {
    "default": "4TfTGcPwoefWe878B0rm",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "arnold": "jBpfuIE2acIp3nSgFhAH",
    "george": "JBFqnCBsd6RMkjW3MqDE",
    "callum": "N2lVS1w4EtoT3dr4eOWO",
}

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

async def ensure_voice_connection(ctx):
    """S'assure que le bot est connecté au canal vocal de l'utilisateur.
    Retourne le voice client ou None."""
    
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("❌ Tu dois être dans un canal vocal !")
        return None
    
    voice_channel = ctx.author.voice.channel
    
    # Vérifier s'il y a une connexion existante
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_connected():
        # Si on est dans le bon canal, garder la connexion
        if voice_client.channel == voice_channel:
            return voice_client
        # Sinon, se déplacer vers le nouveau canal
        else:
            await voice_client.move_to(voice_channel)
            return voice_client
    
    # Se connecter pour la première fois
    try:
        voice_client = await voice_channel.connect(timeout=60, reconnect=True, self_deaf=True)
        return voice_client
    except Exception as e:
        print(f"Erreur connexion vocale: {e}")
        await ctx.send(f"❌ Erreur de connexion vocale: {e}")
        return None

async def play_audio_file(voice_client, audio_file="kaamelott.mp3"):
    """Joue un fichier audio sans déconnecter"""
    
    if not os.path.exists(audio_file):
        print(f"Fichier non trouvé: {audio_file}")
        return False
    
    try:
        audio_source = discord.FFmpegPCMAudio(audio_file)
        voice_client.play(audio_source)
        
        # Attendre la fin
        while voice_client.is_playing():
            await asyncio.sleep(0.1)
        
        await asyncio.sleep(0.3)
        return True
        
    except Exception as e:
        print(f"Erreur lecture audio: {e}")
        return False

async def play_tts(voice_client, text):
    """Génère et joue un fichier TTS avec ElevenLabs sans déconnecter"""
    temp_file = None
    
    try:
        # Générer le TTS avec ElevenLabs
        print(f"Génération TTS avec ElevenLabs (vitesse: {TTS_SPEED})...")
        audio = client.text_to_speech.convert(
            text=text,
            voice_id=TTS_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
            voice_settings={
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0,
                "use_speaker_boost": True
            },
            speech_rate=TTS_SPEED,
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
        
        await asyncio.sleep(0.3)
        return True
        
    except Exception as e:
        print(f"Erreur TTS: {e}")
        return False
    finally:
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
    
    voice_client = await ensure_voice_connection(ctx)
    if not voice_client:
        return
    
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
        
        # Jouer le son Kaamelott SANS déconnecter
        await play_audio_file(voice_client, "kaamelott.mp3")
        
        # Lire le texte à voix haute SANS déconnecter
        await play_tts(voice_client, generated_text)
        
        # Déconnecter automatiquement après avoir fini
        await voice_client.disconnect()
            
    except Exception as e:
        print(f"Erreur: {type(e).__name__}: {e}")
        await ctx.send(f"❌ Erreur: {str(e)}")
    finally:
        # S'assurer qu'on est déconnecté en cas d'erreur
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client and voice_client.is_connected():
            try:
                await voice_client.disconnect()
            except:
                pass

@bot.command(name='disconnect')
async def disconnect(ctx):
    """Déconnecte le bot du canal vocal"""
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("✅ Déconnecté du canal vocal")
    else:
        await ctx.send("❌ Le bot n'est pas connecté à un canal vocal")

@bot.command(name='speed')
async def speed(ctx, new_speed: float = None):
    """Change la vitesse de lecture TTS
    
    Utilisation: !speed [vitesse]
    Vitesse: 0.5 à 2.0 (défaut: 1.0)
    - 0.5 = très lent
    - 1.0 = normal
    - 1.5 = rapide
    - 2.0 = très rapide
    
    Exemple: !speed 1.5
    """
    global TTS_SPEED
    
    if new_speed is None:
        await ctx.send(f"🎚️ **Vitesse actuelle:** {TTS_SPEED}x\n\nUtilise `!speed [valeur]` pour changer\nValeurs: 0.5 à 2.0")
        return
    
    # Vérifier que la vitesse est dans les limites
    if new_speed < 0.5 or new_speed > 2.0:
        await ctx.send(f"❌ Vitesse invalide: `{new_speed}`\n\n**Plage autorisée:** 0.5 à 2.0")
        return
    
    TTS_SPEED = new_speed
    await ctx.send(f"✅ Vitesse de lecture définie à: **{TTS_SPEED}x**")

@bot.command(name='voice')
async def voice(ctx, voice_name: str = None):
    """Change la voix TTS
    
    Utilisation: !voice [nom_voix]
    Voix disponibles: default, bella, adam, arnold, george, callum
    
    Exemple: !voice bella
    """
    global TTS_VOICE_ID
    
    if voice_name is None:
        # Afficher la voix actuelle et les options disponibles
        current_voice = None
        for name, voice_id in VOICES_PRESETS.items():
            if voice_id == TTS_VOICE_ID:
                current_voice = name
                break
        
        voice_list = ", ".join(VOICES_PRESETS.keys())
        await ctx.send(f"🎙️ **Voix actuelle:** {current_voice if current_voice else TTS_VOICE_ID}\n\n**Voix disponibles:** {voice_list}\n\nUtilise `!voice [nom]` pour changer")
        return
    
    voice_name = voice_name.lower()
    
    if voice_name in VOICES_PRESETS:
        TTS_VOICE_ID = VOICES_PRESETS[voice_name]
        await ctx.send(f"✅ Voix changée à: **{voice_name}**")
    else:
        voice_list = ", ".join(VOICES_PRESETS.keys())
        await ctx.send(f"❌ Voix inconnue: `{voice_name}`\n\n**Voix disponibles:** {voice_list}")

@bot.command(name='voice-custom')
async def voice_custom(ctx, voice_id: str):
    """Change la voix TTS avec un ID personnalisé
    
    Utilisation: !voice-custom [voice_id]
    
    Exemple: !voice-custom pNInz6obpgDQGcFmaJgB
    """
    global TTS_VOICE_ID
    
    if not voice_id or len(voice_id) < 10:
        await ctx.send("❌ ID de voix invalide. Utilise un ID valide d'ElevenLabs")
        return
    
    TTS_VOICE_ID = voice_id
    await ctx.send(f"✅ Voix TTS définie à l'ID: `{voice_id}`")

@bot.command(name='prompt')
async def prompt(ctx):
    """Affiche le dernier prompt qui a été envoyé à Gemini"""
    global last_prompt
    
    if last_prompt is None:
        await ctx.send("❌ Aucun prompt n'a été généré pour le moment. Utilise `!chaos` d'abord.")
    else:
        max_length = 1900
        
        if len(last_prompt) <= max_length:
            await ctx.send(f"📮 **Dernier prompt envoyé:**\n```\n{last_prompt}\n```")
        else:
            await ctx.send("📮 **Dernier prompt envoyé:** (en plusieurs parties)")
            chunks = [last_prompt[i:i + max_length] for i in range(0, len(last_prompt), max_length)]
            
            for i, chunk in enumerate(chunks, 1):
                await ctx.send(f"```\n{chunk}\n```")
                
            await ctx.send(f"✅ Prompt affiché en {len(chunks)} partie(s)")

@bot.command(name='help-voice')
async def help_voice(ctx):
    """Affiche l'aide pour les commandes vocales"""
    help_text = """🎙️ **Commandes Vocales:**

`!voice` - Affiche la voix actuelle et les voix disponibles
`!voice [nom]` - Change la voix (default, bella, adam, arnold, george, callum)
`!voice-custom [id]` - Change la voix avec un ID personnalisé d'ElevenLabs
`!speed` - Affiche la vitesse actuelle
`!speed [vitesse]` - Change la vitesse (0.5 à 2.0)
`!disconnect` - Déconnecte le bot du canal vocal
`!chaos` - Génère un texte absurde et le lit à voix haute
`!prompt` - Affiche le dernier prompt envoyé à Gemini

**Exemples:**
`!voice bella` - Change la voix à Bella
`!speed 1.5` - Augmente la vitesse à 1.5x (plus rapide)
`!speed 0.8` - Réduit la vitesse à 0.8x (plus lent)
`!voice-custom pNInz6obpgDQGcFmaJgB` - Utilise un voice ID personnalisé
"""
    await ctx.send(help_text)

# Lancer le bot
bot.run(DISCORD_TOKEN)