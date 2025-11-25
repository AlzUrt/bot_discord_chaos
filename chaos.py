import discord
from discord.ext import commands
import google.generativeai as genai
import os
from dotenv import load_dotenv
from collections import deque
import asyncio
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
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
TTS_VOICE_ID = "iMij959nvbX8f2SxyrvX"  # Voice ID de la voix sélectionnée
TTS_SPEED = 1.2  # Vitesse de lecture (0.5 à 2.0, défaut 1.0)
TTS_SIMILARITY_BOOST = 1.00  # Similarity Boost (0.0 à 1.0, défaut 0.75)
TTS_STABILITY = 1.00  # Stabilité (0.0 à 1.0, défaut 0.5)
TTS_STYLE = 0.5  # Style (0.0 à 1.0, défaut 0.0)
TTS_USE_SPEAKER_BOOST = True  # Utiliser speaker boost

# Dictionnaire des voix prédéfinies (exemple)
VOICES_PRESETS = {
    "default": "iMij959nvbX8f2SxyrvX",
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

IMPORTANT: Les phrases suivantes ont DÉJÀ été générées. Tu DOIS absolument éviter de les reproduire ou de générer quelque chose de similaire. Crée quelque chose de complètement différent :
{history}

Ne me fait pas de liste, ne numérote pas les phrases, ne les sépare pas par des tirets. Écris simplement le paragraphe avec les phrases à la suite les unes des autres.
Et commence le paragraphe par "Vive le chaos !"."""

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

def generate_tts_file_sync(text):
    """Génère un fichier TTS avec ElevenLabs (fonction synchrone pour run_in_executor)"""
    temp_file = None
    
    try:
        print(f"🎤 Génération TTS avec ElevenLabs (vitesse: {TTS_SPEED}, stabilité: {TTS_STABILITY})...")
        audio = client.text_to_speech.convert(
            text=text,
            voice_id=TTS_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
            voice_settings=VoiceSettings(
                stability=TTS_STABILITY,
                similarity_boost=TTS_SIMILARITY_BOOST,
                style=TTS_STYLE,
                use_speaker_boost=TTS_USE_SPEAKER_BOOST,
                speed=TTS_SPEED,
            ),
        )
        
        # Sauvegarder dans un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            temp_file = tmp.name
            chunks_written = 0
            for chunk in audio:
                tmp.write(chunk)
                chunks_written += 1
            print(f"✅ TTS: {chunks_written} chunks écrits")
        
        if not os.path.exists(temp_file) or os.path.getsize(temp_file) == 0:
            print("❌ Le fichier TTS est vide ou n'existe pas")
            return None
        
        print(f"✅ Fichier TTS prêt ({os.path.getsize(temp_file)} bytes)")
        return temp_file
        
    except Exception as e:
        print(f"❌ Erreur génération TTS: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        return None


async def generate_tts_file(text):
    """Génère un fichier TTS avec ElevenLabs (async wrapper)"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, generate_tts_file_sync, text)


async def play_tts_file(voice_client, tts_file):
    """Joue un fichier TTS déjà généré"""
    try:
        if not voice_client or not voice_client.is_connected():
            print("❌ Le bot n'est pas connecté au canal vocal")
            return False
        
        if not tts_file or not os.path.exists(tts_file):
            print("❌ Le fichier TTS n'existe pas")
            return False
        
        print(f"🔊 Lecture du fichier TTS ({os.path.getsize(tts_file)} bytes)...")
        
        audio_source = discord.FFmpegPCMAudio(tts_file)
        voice_client.play(audio_source)
        
        # Attendre la fin avec timeout
        timeout = 0
        while voice_client.is_playing() and timeout < 120:
            await asyncio.sleep(0.2)
            timeout += 0.2
        
        print("✅ Lecture TTS terminée")
        await asyncio.sleep(0.3)
        return True
        
    except Exception as e:
        print(f"❌ Erreur lecture TTS: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Nettoyer le fichier temporaire
        if tts_file and os.path.exists(tts_file):
            try:
                await asyncio.sleep(0.3)
                os.remove(tts_file)
                print(f"🗑️ Fichier temporaire supprimé")
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
    
    tts_file = None  # Pour le nettoyage en cas d'erreur
    voice_client = None
    
    try:
        async with ctx.typing():
            # 1. Construire le prompt et appeler Gemini
            current_prompt = build_chaos_prompt()
            last_prompt = current_prompt
            
            print("📝 Appel à Gemini...")
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = model.generate_content(
                current_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.8,
                    max_output_tokens=300
                )
            )
            
            if not response or not response.text:
                await ctx.send("⚠️ La réponse de Gemini était vide. Réessaye avec `!chaos`")
                print("❌ Réponse Gemini vide")
                return
            
            generated_text = response.text.strip()
            print(f"✅ Texte généré: {generated_text[:100]}...")
            
            # Ajouter le texte à l'historique
            generated_history.append(generated_text)
            
            # 2. 🚀 Lancer la génération TTS en arrière-plan
            print("🚀 Lancement de la génération TTS en arrière-plan...")
            tts_task = asyncio.create_task(generate_tts_file(generated_text))
            
            # 3. ⏳ Attendre que le TTS soit prêt
            print("⏳ Attente de la fin de génération TTS...")
            tts_file = await tts_task
            
            if not tts_file:
                print("❌ La génération TTS a échoué")
                await ctx.send("❌ Erreur lors de la génération TTS")
                return
            
            print("✅ TTS prêt!")
        
        # 4. Connexion au vocal
        voice_client = await ensure_voice_connection(ctx)
        if not voice_client:
            print("❌ Impossible de se connecter au canal vocal")
            return
        
        print(f"✅ Connecté au canal vocal: {voice_client.channel}")
        
        # 5. 🎵 Jouer le son Kaamelott
        print("🎵 Lecture de Kaamelott...")
        kaamelott_ok = await play_audio_file(voice_client, "kaamelott.mp3")
        if kaamelott_ok:
            print("✅ Kaamelott joué")
        else:
            print("⚠️ Kaamelott n'a pas pu être joué")
        
        # 6. Envoyer le message dans le chat
        await ctx.send(generated_text)
        
        # Vérifier la connexion avant TTS
        if not voice_client.is_connected():
            print("❌ Perte de connexion après Kaamelott!")
            await ctx.send("❌ Le bot s'est déconnecté")
            return
        
        # 7. 🔊 Lire le TTS immédiatement (fichier déjà prêt!)
        print("🔊 Lecture du TTS...")
        tts_ok = await play_tts_file(voice_client, tts_file)
        tts_file = None  # Le fichier est nettoyé par play_tts_file
        
        if tts_ok:
            print("✅ TTS joué avec succès")
        else:
            print("❌ TTS n'a pas pu être joué")
            await ctx.send("❌ Erreur lors de la lecture TTS")
        
        # 8. Déconnecter automatiquement après avoir fini
        print("🔌 Déconnexion du canal vocal...")
        await voice_client.disconnect()
        print("✅ Déconnecté")
            
    except Exception as e:
        print(f"❌ Erreur: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        await ctx.send(f"❌ Erreur: {str(e)}")
    finally:
        # Nettoyer le fichier TTS si nécessaire
        if tts_file and os.path.exists(tts_file):
            try:
                os.remove(tts_file)
                print(f"🗑️ Fichier TTS nettoyé (erreur)")
            except:
                pass
        
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

@bot.command(name='similarity-boost')
async def similarity_boost(ctx, new_similarity_boost: float = None):
    """Change la valeur de Similarity Boost de la voix TTS
    
    Utilisation: !similarity-boost [valeur]
    Similarity Boost: 0.0 à 1.0 (défaut: 0.75)
    - 0.0 = pas de boost
    - 1.0 = boost maximal
    
    Exemple: !similarity-boost 0.8
    """
    global TTS_SIMILARITY_BOOST
    
    if new_similarity_boost is None:
        await ctx.send(f"🎯 **Similarity Boost actuel:** {TTS_SIMILARITY_BOOST}\n\nUtilise `!similarity-boost [valeur]` pour changer\nValeurs: 0.0 à 1.0")
        return
    
    if new_similarity_boost < 0.0 or new_similarity_boost > 1.0:
        await ctx.send(f"❌ Similarity Boost invalide: `{new_similarity_boost}`\n\n**Plage autorisée:** 0.0 à 1.0")
        return
    
    TTS_SIMILARITY_BOOST = new_similarity_boost
    await ctx.send(f"✅ Similarity Boost défini à: **{TTS_SIMILARITY_BOOST}**")

@bot.command(name='stability')
async def stability(ctx, new_stability: float = None):
    """Change la stabilité de la voix TTS
    
    Utilisation: !stability [valeur]
    Stabilité: 0.0 à 1.0 (défaut: 0.5)
    - 0.0 = très variable (plus d'émotion, moins stable)
    - 0.5 = équilibré
    - 1.0 = très stable (voix robote)
    
    Exemple: !stability 0.7
    """
    global TTS_STABILITY
    
    if new_stability is None:
        await ctx.send(f"🎯 **Stabilité actuelle:** {TTS_STABILITY}\n\nUtilise `!stability [valeur]` pour changer\nValeurs: 0.0 à 1.0")
        return
    
    if new_stability < 0.0 or new_stability > 1.0:
        await ctx.send(f"❌ Stabilité invalide: `{new_stability}`\n\n**Plage autorisée:** 0.0 à 1.0")
        return
    
    TTS_STABILITY = new_stability
    await ctx.send(f"✅ Stabilité définie à: **{TTS_STABILITY}**")

@bot.command(name='style')
async def style(ctx, new_style: float = None):
    """Change le style de la voix TTS
    
    Utilisation: !style [valeur]
    Style: 0.0 à 1.0 (défaut: 0.0)
    - 0.0 = neutre
    - 0.5 = style modéré
    - 1.0 = style accentué
    
    Exemple: !style 0.5
    """
    global TTS_STYLE
    
    if new_style is None:
        await ctx.send(f"🎨 **Style actuel:** {TTS_STYLE}\n\nUtilise `!style [valeur]` pour changer\nValeurs: 0.0 à 1.0")
        return
    
    if new_style < 0.0 or new_style > 1.0:
        await ctx.send(f"❌ Style invalide: `{new_style}`\n\n**Plage autorisée:** 0.0 à 1.0")
        return
    
    TTS_STYLE = new_style
    await ctx.send(f"✅ Style défini à: **{TTS_STYLE}**")

@bot.command(name='speaker-boost')
async def speaker_boost(ctx, enable: str = None):
    """Active ou désactive le speaker boost TTS
    
    Utilisation: !speaker-boost [on|off]
    
    Exemples:
    !speaker-boost on
    !speaker-boost off
    """
    global TTS_USE_SPEAKER_BOOST
    
    if enable is None:
        status = "✅ Activé" if TTS_USE_SPEAKER_BOOST else "❌ Désactivé"
        await ctx.send(f"🔊 **Speaker boost:** {status}\n\nUtilise `!speaker-boost [on|off]` pour changer")
        return
    
    enable_lower = enable.lower()
    
    if enable_lower in ["on", "true", "1", "yes", "oui"]:
        TTS_USE_SPEAKER_BOOST = True
        await ctx.send(f"✅ Speaker boost **activé**")
    elif enable_lower in ["off", "false", "0", "no", "non"]:
        TTS_USE_SPEAKER_BOOST = False
        await ctx.send(f"✅ Speaker boost **désactivé**")
    else:
        await ctx.send(f"❌ Valeur invalide: `{enable}`\n\nUtilise: `on` ou `off`")

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
async def tts_settings(ctx):
    """Affiche les paramètres TTS actuels"""
    
    # Trouver le nom de la voix actuelle
    current_voice = None
    for name, voice_id in VOICES_PRESETS.items():
        if voice_id == TTS_VOICE_ID:
            current_voice = name
            break
    
    speaker_boost_status = "✅ Activé" if TTS_USE_SPEAKER_BOOST else "❌ Désactivé"
    
    settings_text = f"""⚙️ **Paramètres TTS actuels:**

🎙️ **Voix:** {current_voice if current_voice else TTS_VOICE_ID}
🎚️ **Vitesse:** {TTS_SPEED}x
🎯 **Similarity Boost:** {TTS_SIMILARITY_BOOST}
🎯 **Stabilité:** {TTS_STABILITY}
🎨 **Style:** {TTS_STYLE}
🔊 **Speaker Boost:** {speaker_boost_status}

**Modifier les paramètres:**
`!speed [0.5-2.0]` - Changer la vitesse
`!similarity-boost [0.0-1.0]` - Changer le Similarity Boost
`!stability [0.0-1.0]` - Changer la stabilité
`!style [0.0-1.0]` - Changer le style
`!speaker-boost [on|off]` - Changer speaker boost
`!voice [nom]` - Changer la voix
"""
    
    await ctx.send(settings_text)
    """Affiche l'aide pour les commandes vocales"""
    help_text = """🎙️ **Commandes Vocales:**

**Voix:**
`!voice` - Affiche la voix actuelle et les voix disponibles
`!voice [nom]` - Change la voix (default, bella, adam, arnold, george, callum)
`!voice-custom [id]` - Change la voix avec un ID personnalisé d'ElevenLabs

**Paramètres TTS:**
`!speed [valeur]` - Change la vitesse (0.5 à 2.0, défaut: 1.0)
`!stability [valeur]` - Change la stabilité (0.0 à 1.0, défaut: 0.5)
`!style [valeur]` - Change le style (0.0 à 1.0, défaut: 0.0)
`!speaker-boost [on|off]` - Active/désactive le speaker boost

**Commandes Principales:**
`!chaos` - Génère un texte absurde et le lit à voix haute
`!prompt` - Affiche le dernier prompt envoyé à Gemini
`!disconnect` - Déconnecte le bot du canal vocal

**Exemples:**
```
!voice bella              # Change la voix à Bella
!speed 1.5               # Augmente la vitesse à 1.5x
!stability 0.7           # Rend la voix plus stable
!style 0.5               # Ajoute du style à la voix
!speaker-boost on        # Active le speaker boost
!similarity-boost 0.8    # Change le Similarity Boost à 0.8
!voice-custom pNInz6obpgDQGcFmaJgB  # Utilise un voice ID personnalisé
```
"""
    await ctx.send(help_text)

# Lancer le bot
bot.run(DISCORD_TOKEN)