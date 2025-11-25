import discord
from discord.ext import commands
from google import genai
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

# ===== SYSTÈME DE ROTATION DES CLÉS ELEVENLABS =====
ELEVENLABS_API_KEYS = [
    os.getenv('ELEVENLABS_API_KEY'),
    os.getenv('ELEVENLABS_API_KEY_2'),
    os.getenv('ELEVENLABS_API_KEY_3'),
    os.getenv('ELEVENLABS_API_KEY_4'),
]
# Filtrer les clés None ou vides
ELEVENLABS_API_KEYS = [k for k in ELEVENLABS_API_KEYS if k]
current_elevenlabs_key_index = 0

# Initialiser le client Gemini (nouvelle API)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Initialiser ElevenLabs avec la première clé
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEYS[0]) if ELEVENLABS_API_KEYS else None

def rotate_elevenlabs_key():
    """Passe à la clé API ElevenLabs suivante. Retourne True si on a pu changer, False si plus de clés."""
    global current_elevenlabs_key_index, elevenlabs_client
    
    current_elevenlabs_key_index += 1
    
    if current_elevenlabs_key_index >= len(ELEVENLABS_API_KEYS):
        print("❌ Toutes les clés ElevenLabs sont épuisées !")
        return False
    
    new_key = ELEVENLABS_API_KEYS[current_elevenlabs_key_index]
    elevenlabs_client = ElevenLabs(api_key=new_key)
    print(f"🔄 Rotation vers la clé ElevenLabs #{current_elevenlabs_key_index + 1}/{len(ELEVENLABS_API_KEYS)}")
    return True

def get_current_key_info():
    """Retourne les infos sur la clé actuelle"""
    return f"Clé {current_elevenlabs_key_index + 1}/{len(ELEVENLABS_API_KEYS)}"

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

# ===== SYSTÈME DE BUFFER DE PROMPTS PRÉ-GÉNÉRÉS =====
# Structure: {"text": str, "tts_file": str}
prompt_buffer = deque(maxlen=2)  # Buffer de 2 prompts prêts
buffer_lock = asyncio.Lock()  # Lock pour éviter les race conditions
is_generating = False  # Flag pour savoir si une génération est en cours

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

def generate_tts_file_sync(text, retry_on_quota=True):
    """Génère un fichier TTS avec ElevenLabs (fonction synchrone pour run_in_executor)
    
    Args:
        text: Le texte à convertir en audio
        retry_on_quota: Si True, essaie de changer de clé API en cas de quota dépassé
    """
    temp_file = None
    
    try:
        print(f"🎤 Génération TTS avec ElevenLabs [{get_current_key_info()}] (vitesse: {TTS_SPEED}, stabilité: {TTS_STABILITY})...")
        audio = elevenlabs_client.text_to_speech.convert(
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
        error_str = str(e)
        print(f"❌ Erreur génération TTS: {type(e).__name__}: {e}")
        
        # Vérifier si c'est une erreur de quota
        if retry_on_quota and ("quota_exceeded" in error_str or "quota" in error_str.lower()):
            print("⚠️ Quota dépassé, tentative de rotation de clé...")
            
            # Nettoyer le fichier temporaire si créé
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            
            # Essayer de changer de clé
            if rotate_elevenlabs_key():
                print("🔄 Nouvelle clé activée, nouvelle tentative...")
                return generate_tts_file_sync(text, retry_on_quota=True)
            else:
                print("❌ Plus de clés disponibles !")
                return None
        
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


async def play_tts_file(voice_client, tts_file, delete_after=True):
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
            await asyncio.sleep(0.1)
            timeout += 0.1
        
        print("✅ Lecture TTS terminée")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lecture TTS: {type(e).__name__}: {e}")
        return False
    finally:
        # Nettoyer le fichier temporaire seulement si demandé
        if delete_after and tts_file and os.path.exists(tts_file):
            try:
                os.remove(tts_file)
                print("🧹 Fichier temporaire supprimé")
            except:
                pass


def generate_chaos_text_sync(prompt):
    """Génère du texte avec Gemini (fonction synchrone pour run_in_executor)"""
    try:
        response = gemini_client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"❌ Erreur Gemini: {type(e).__name__}: {e}")
        return None


async def generate_chaos_text(prompt):
    """Génère du texte avec Gemini (async wrapper)"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, generate_chaos_text_sync, prompt)


# ===== SYSTÈME DE BUFFER =====

async def generate_and_buffer_prompt():
    """Génère un prompt complet (texte + TTS) et l'ajoute au buffer"""
    global is_generating, last_prompt
    
    # Vérifier si on peut générer (sans bloquer)
    async with buffer_lock:
        if is_generating:
            print("⏳ Génération déjà en cours, skip...")
            return False
        if len(prompt_buffer) >= 2:
            print("📦 Buffer déjà plein, skip...")
            return False
        is_generating = True
    
    try:
        print(f"🔄 Génération d'un nouveau prompt pour le buffer (actuel: {len(prompt_buffer)}/2)...")
        
        # 1. Construire et générer le texte
        prompt = build_chaos_prompt()
        last_prompt = prompt
        
        print("🤖 Génération du texte avec Gemini...")
        chaos_text = await generate_chaos_text(prompt)
        
        if not chaos_text:
            print("❌ Échec génération texte pour le buffer")
            return False
        
        # 2. Générer le TTS
        print("🎤 Génération du TTS pour le buffer...")
        tts_file = await generate_tts_file(chaos_text)
        
        if not tts_file:
            print("❌ Échec génération TTS pour le buffer")
            return False
        
        # 3. Ajouter au buffer
        async with buffer_lock:
            prompt_buffer.append({
                "text": chaos_text,
                "tts_file": tts_file
            })
            print(f"✅ Prompt ajouté au buffer (maintenant: {len(prompt_buffer)}/2)")
        
        return True
            
    except Exception as e:
        print(f"❌ Erreur lors de la génération pour le buffer: {e}")
        return False
    finally:
        async with buffer_lock:
            is_generating = False


async def refill_buffer():
    """Remplit le buffer jusqu'à 2 prompts (lance une seule génération à la fois)"""
    if len(prompt_buffer) < 2:
        await generate_and_buffer_prompt()
    # Si encore besoin après, la background task s'en chargera


async def get_buffered_prompt():
    """Récupère un prompt du buffer (ou None si vide)"""
    async with buffer_lock:
        if prompt_buffer:
            return prompt_buffer.popleft()
        return None


async def background_buffer_task():
    """Tâche de fond qui maintient le buffer rempli"""
    await bot.wait_until_ready()
    print("🔄 Démarrage de la tâche de remplissage du buffer...")
    
    # Remplissage initial (2 prompts)
    await generate_and_buffer_prompt()
    await generate_and_buffer_prompt()
    print(f"✅ Buffer initial rempli: {len(prompt_buffer)}/2 prompts prêts")
    
    # Boucle de maintenance
    while not bot.is_closed():
        try:
            # Vérifier si on a besoin de regénérer
            if len(prompt_buffer) < 2 and not is_generating:
                await generate_and_buffer_prompt()
            await asyncio.sleep(2)  # Vérifie toutes les 2 secondes
        except Exception as e:
            print(f"❌ Erreur dans la tâche de buffer: {e}")
            await asyncio.sleep(5)


@bot.event
async def on_ready():
    print(f'✅ Bot connecté en tant que {bot.user}')
    print(f'📦 Serveurs: {len(bot.guilds)}')
    print(f'🤖 Modèle Gemini: gemini-3-pro-preview')
    print(f'🔑 Clés ElevenLabs: {len(ELEVENLABS_API_KEYS)} clés chargées')
    print(f'📦 Système de buffer activé (2 prompts en avance)')
    
    # Démarrer la tâche de fond pour maintenir le buffer
    bot.loop.create_task(background_buffer_task())


@bot.command(name='chaos')
async def chaos(ctx):
    """Génère un texte absurde avec Gemini et le lit à voix haute"""
    
    # Vérifier que l'utilisateur est dans un canal vocal
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("❌ Tu dois être dans un canal vocal !")
        return
    
    # 1. Essayer de récupérer un prompt du buffer
    buffered = await get_buffered_prompt()
    
    if buffered:
        # On a un prompt prêt !
        chaos_text = buffered["text"]
        tts_file = buffered["tts_file"]
        print(f"⚡ Utilisation d'un prompt buffered (reste: {len(prompt_buffer)}/2)")
        
        # 2. Se connecter au canal vocal IMMÉDIATEMENT
        voice_client = await ensure_voice_connection(ctx)
        if not voice_client:
            # Nettoyer le fichier TTS si connexion échouée
            if os.path.exists(tts_file):
                os.remove(tts_file)
            return
        
        # 3. Lancer le remplissage du buffer en arrière-plan (pendant qu'on joue)
        bot.loop.create_task(generate_and_buffer_prompt())
        
        # 4. Jouer le son d'intro (kaamelott)
        await play_audio_file(voice_client, "kaamelott.mp3")
        
        # 5. Envoyer le texte sur Discord
        await ctx.send(f"📜 **Le Chaos a parlé:**\n\n{chaos_text}")
        
        # 6. Jouer le TTS
        await play_tts_file(voice_client, tts_file, delete_after=True)
        
        # 7. Ajouter à l'historique
        generated_history.append(chaos_text)
        
        # 8. Déconnecter le bot
        await voice_client.disconnect()
        print("👋 Bot déconnecté du canal vocal")
        
    else:
        # Buffer vide, on doit générer à la volée (fallback)
        await ctx.send("🎲 *Invocation du chaos en cours... (buffer vide, génération en cours)*")
        
        prompt = build_chaos_prompt()
        global last_prompt
        last_prompt = prompt
        
        print("🤖 Génération du texte avec Gemini (fallback)...")
        chaos_text = await generate_chaos_text(prompt)
        
        if not chaos_text:
            await ctx.send("❌ Erreur lors de la génération du texte")
            return
        
        print("🎤 Génération du TTS (fallback)...")
        tts_file = await generate_tts_file(chaos_text)
        
        if not tts_file:
            await ctx.send("❌ Erreur lors de la génération du TTS")
            return
        
        # Se connecter au canal vocal
        voice_client = await ensure_voice_connection(ctx)
        if not voice_client:
            if os.path.exists(tts_file):
                os.remove(tts_file)
            return
        
        # Jouer le son d'intro
        await play_audio_file(voice_client, "kaamelott.mp3")
        
        # Envoyer le texte
        await ctx.send(f"📜 **Le Chaos a parlé:**\n\n{chaos_text}")
        
        # Jouer le TTS
        await play_tts_file(voice_client, tts_file, delete_after=True)
        
        # Ajouter à l'historique
        generated_history.append(chaos_text)
        
        # Déconnecter
        await voice_client.disconnect()
        print("👋 Bot déconnecté du canal vocal")
        
        # Relancer le remplissage du buffer après
        bot.loop.create_task(refill_buffer())


@bot.command(name='buffer')
async def buffer_status(ctx):
    """Affiche le statut du buffer de prompts"""
    global is_generating
    
    status = "🔄 En cours..." if is_generating else "✅ Prêt"
    
    await ctx.send(f"""📦 **Statut du Buffer:**

**Prompts en stock:** {len(prompt_buffer)}/2
**Génération:** {status}

Le buffer pré-génère des prompts pour que `!chaos` soit instantané !""")


@bot.command(name='keys')
async def keys_status(ctx):
    """Affiche le statut des clés API ElevenLabs"""
    global current_elevenlabs_key_index
    
    total_keys = len(ELEVENLABS_API_KEYS)
    current_key = current_elevenlabs_key_index + 1
    remaining_keys = total_keys - current_elevenlabs_key_index
    
    # Construire la liste visuelle des clés
    keys_visual = []
    for i in range(total_keys):
        if i < current_elevenlabs_key_index:
            keys_visual.append(f"~~Clé {i+1}~~ ❌ (épuisée)")
        elif i == current_elevenlabs_key_index:
            keys_visual.append(f"**Clé {i+1}** ✅ (active)")
        else:
            keys_visual.append(f"Clé {i+1} 💤 (en réserve)")
    
    keys_list = "\n".join(keys_visual)
    
    await ctx.send(f"""🔑 **Statut des clés ElevenLabs:**

{keys_list}

**Clé active:** {current_key}/{total_keys}
**Clés restantes:** {remaining_keys}

Les clés sont automatiquement changées quand le quota est dépassé.""")


@bot.command(name='reset-keys')
async def reset_keys(ctx):
    """Remet les clés API ElevenLabs à la première"""
    global current_elevenlabs_key_index, elevenlabs_client
    
    current_elevenlabs_key_index = 0
    elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEYS[0])
    
    await ctx.send(f"🔄 Clés ElevenLabs réinitialisées ! Utilisation de la clé 1/{len(ELEVENLABS_API_KEYS)}")


@bot.command(name='refill')
async def refill_cmd(ctx):
    """Force le remplissage du buffer"""
    await ctx.send("🔄 Remplissage du buffer en cours...")
    bot.loop.create_task(refill_buffer())
    await ctx.send("✅ Tâche de remplissage lancée !")


@bot.command(name='disconnect')
async def disconnect(ctx):
    """Déconnecte le bot du canal vocal"""
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("👋 Déconnecté du canal vocal")
    else:
        await ctx.send("❌ Je ne suis pas connecté à un canal vocal")

@bot.command(name='speed')
async def speed(ctx, new_speed: float = None):
    """Change la vitesse de lecture TTS
    
    Utilisation: !speed [valeur]
    Valeurs: 0.5 à 2.0 (défaut: 1.0)
    
    Exemple: !speed 1.5
    """
    global TTS_SPEED
    
    if new_speed is None:
        await ctx.send(f"🎚️ **Vitesse actuelle:** {TTS_SPEED}x\n\nUtilise `!speed [valeur]` pour changer\nValeurs: 0.5 à 2.0")
        return
    
    if new_speed < 0.5 or new_speed > 2.0:
        await ctx.send(f"❌ Vitesse invalide: `{new_speed}`\n\n**Plage autorisée:** 0.5 à 2.0")
        return
    
    TTS_SPEED = new_speed
    await ctx.send(f"✅ Vitesse définie à: **{TTS_SPEED}x**")

@bot.command(name='voice')
async def voice(ctx, voice_name: str = None):
    """Change la voix TTS
    
    Utilisation: !voice [nom]
    
    Voix disponibles: default, bella, adam, arnold, george, callum
    """
    global TTS_VOICE_ID
    
    if voice_name is None:
        current_voice = None
        for name, voice_id in VOICES_PRESETS.items():
            if voice_id == TTS_VOICE_ID:
                current_voice = name
                break
        
        voice_list = ", ".join(VOICES_PRESETS.keys())
        await ctx.send(f"🎙️ **Voix actuelle:** {current_voice if current_voice else TTS_VOICE_ID}\n\n**Voix disponibles:** {voice_list}")
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
`!buffer` - Affiche le statut du buffer de prompts
`!keys` - Affiche le statut des clés API ElevenLabs
`!reset-keys` - Réinitialise les clés API à la première
`!refill` - Force le remplissage du buffer
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