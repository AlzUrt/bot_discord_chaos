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
        # Vérifier que le voice_client est toujours connecté
        if not voice_client or not voice_client.is_connected():
            print("❌ Le bot n'est pas connecté au canal vocal")
            return False
        
        # Générer le TTS avec ElevenLabs
        print(f"Génération TTS avec ElevenLabs...")
        audio = client.text_to_speech.convert(
            text=text,
            voice_id=TTS_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        
        # Sauvegarder ENTIÈREMENT dans un fichier temporaire avant de jouer
        print("Écriture du fichier TTS...")
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            temp_file = tmp.name
            # Consommer ENTIÈREMENT l'itérateur
            chunks_written = 0
            for chunk in audio:
                tmp.write(chunk)
                chunks_written += 1
            print(f"✅ {chunks_written} chunks écrits")
        
        # Vérifier que le fichier existe et n'est pas vide
        if not os.path.exists(temp_file) or os.path.getsize(temp_file) == 0:
            print("❌ Le fichier TTS est vide ou n'existe pas")
            return False
        
        print(f"Fichier TTS créé ({os.path.getsize(temp_file)} bytes), lecture en cours...")
        
        # Vérifier la connexion avant de jouer
        if not voice_client.is_connected():
            print("❌ Perte de connexion vocale avant la lecture TTS")
            return False
        
        # Jouer le son
        audio_source = discord.FFmpegPCMAudio(temp_file)
        voice_client.play(audio_source)
        print("Lecture du TTS lancée...")
        
        # Attendre la fin avec timeout
        timeout = 0
        while voice_client.is_playing() and timeout < 120:  # Max 2 minutes
            await asyncio.sleep(0.2)
            timeout += 0.2
        
        print("Lecture TTS terminée")
        await asyncio.sleep(0.5)
        return True
        
    except Exception as e:
        print(f"❌ Erreur TTS: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Nettoyer le fichier temporaire
        if temp_file and os.path.exists(temp_file):
            try:
                await asyncio.sleep(0.5)  # Attendre un peu avant de supprimer
                os.remove(temp_file)
                print(f"Fichier temporaire supprimé")
            except Exception as e:
                print(f"Erreur suppression fichier: {e}")

@bot.event
async def on_ready():
    print(f'{bot.user} s\'est connecté à Discord!')

@bot.command(name='chaos')
async def chaos(ctx):
    """Génère un texte aléatoire avec Gemini, joue un son, puis lit le texte à voix haute"""
    global last_prompt
    
    print("\n" + "="*50)
    print("🎮 Commande !chaos démarrée")
    print("="*50)
    
    voice_client = await ensure_voice_connection(ctx)
    if not voice_client:
        print("❌ Impossible de se connecter au canal vocal")
        return
    
    print(f"✅ Connecté au canal vocal: {voice_client.channel}")
    
    try:
        async with ctx.typing():
            # Construire le prompt avec l'historique
            current_prompt = build_chaos_prompt()
            
            # Enregistrer le dernier prompt
            last_prompt = current_prompt
            
            # Appeler l'API Gemini
            print("📝 Appel à Gemini...")
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
                print("❌ Réponse Gemini vide")
                return
            
            # Extraire le texte généré
            generated_text = response.text.strip()
            print(f"✅ Texte généré: {generated_text[:100]}...")
            
            # Ajouter le texte à l'historique
            generated_history.append(generated_text)
            
            # Envoyer le message
            await ctx.send(generated_text)
        
        # Jouer le son Kaamelott
        print("🎵 Lecture de Kaamelott...")
        kaamelott_ok = await play_audio_file(voice_client, "kaamelott.mp3")
        if kaamelott_ok:
            print("✅ Kaamelott joué")
        else:
            print("⚠️ Kaamelott n'a pas pu être joué")
        
        # Vérifier la connexion avant TTS
        if not voice_client.is_connected():
            print("❌ Perte de connexion après Kaamelott!")
            await ctx.send("❌ Le bot s'est déconnecté")
            return
        
        print(f"✅ Encore connecté au canal: {voice_client.channel}")
        
        # Lire le texte à voix haute
        print("🎤 Lecture du TTS...")
        tts_ok = await play_tts(voice_client, generated_text)
        
        if tts_ok:
            print("✅ TTS joué avec succès")
        else:
            print("❌ TTS n'a pas pu être joué")
            await ctx.send("❌ Erreur lors de la lecture TTS")
        
        # Déconnecter automatiquement après avoir fini
        print("🔌 Déconnexion du canal vocal...")
        await voice_client.disconnect()
        print("✅ Déconnecté")
            
    except Exception as e:
        print(f"❌ Erreur: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        await ctx.send(f"❌ Erreur: {str(e)}")
    finally:
        # S'assurer qu'on est déconnecté en cas d'erreur
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client and voice_client.is_connected():
            try:
                print("🔌 Déconnexion forcée...")
                await voice_client.disconnect()
            except Exception as e:
                print(f"Erreur déconnexion: {e}")
        
        print("="*50)
        print("✅ Commande !chaos terminée\n")


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
    
    ⚠️ NOTE: La vitesse de lecture n'est pas encore disponible via l'API ElevenLabs.
    Cette commande est en développement.
    
    Utilisation: !speed [vitesse]
    Vitesse: 0.5 à 2.0 (défaut: 1.0)
    """
    global TTS_SPEED
    
    await ctx.send("⚠️ **La vitesse de lecture n'est pas encore disponible via l'API ElevenLabs.**\n\nElevenLabs ne supporte pas actuellement le paramètre `speech_rate` dans l'API Python.\n\nAlternatives:\n- Modifie le texte généré avant la lecture\n- Utilise une voix différente qui parle naturellement plus vite")
    return

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
`!disconnect` - Déconnecte le bot du canal vocal
`!chaos` - Génère un texte absurde et le lit à voix haute
`!prompt` - Affiche le dernier prompt envoyé à Gemini

**Exemples:**
`!voice bella` - Change la voix à Bella
`!voice-custom pNInz6obpgDQGcFmaJgB` - Utilise un voice ID personnalisé

**Note:** La vitesse de lecture n'est pas encore supportée par l'API ElevenLabs.
Tu peux changer de voix pour obtenir des vitesses différentes.
"""
    await ctx.send(help_text)

# Lancer le bot
bot.run(DISCORD_TOKEN)