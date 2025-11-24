import discord
from discord.ext import commands
import google.generativeai as genai
import os
from dotenv import load_dotenv
from collections import deque
import asyncio

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
intents.members = True  # Important pour les informations des membres
intents.presences = True  # Important pour le statut des utilisateurs
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
    import traceback
    import subprocess
    
    print("\n" + "="*60)
    print("[AUDIO] 🔍 DÉMARRAGE DEBUG COMPLET")
    print("="*60)
    
    voice_client = None
    
    try:
        # ===== ÉTAPE 1 : VÉRIFICATIONS PRÉALABLES =====
        print("\n[AUDIO] 📋 ÉTAPE 1: Vérifications préalables")
        print("-" * 60)
        
        # Vérifier FFmpeg
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
            ffmpeg_version = result.stdout.decode().split('\n')[0]
            print(f"[AUDIO] ✅ FFmpeg trouvé: {ffmpeg_version}")
        except Exception as e:
            print(f"[AUDIO] ❌ FFmpeg non trouvé: {e}")
            print(f"[AUDIO] ⚠️  Installez FFmpeg et ajoutez-le au PATH")
            return
        
        # Vérifier que l'utilisateur est dans un canal vocal
        print(f"[AUDIO] Vérification canal vocal utilisateur...")
        print(f"  - ctx.author.voice: {ctx.author.voice}")
        
        if ctx.author.voice is None:
            print(f"[AUDIO] ❌ ctx.author.voice est None")
            return
        
        print(f"  - ctx.author.voice.channel: {ctx.author.voice.channel}")
        
        if ctx.author.voice.channel is None:
            print(f"[AUDIO] ❌ L'utilisateur n'est pas dans un canal vocal")
            return
        
        voice_channel = ctx.author.voice.channel
        print(f"[AUDIO] ✅ Canal vocal trouvé: {voice_channel.name} (ID: {voice_channel.id})")
        print(f"  - Type de canal: {type(voice_channel)}")
        print(f"  - Guild: {ctx.guild.name} (ID: {ctx.guild.id})")
        
        # Vérifier le fichier audio
        print(f"\n[AUDIO] Vérification fichier audio...")
        audio_path = os.path.abspath(audio_file)
        print(f"  - Chemin fourni: {audio_file}")
        print(f"  - Chemin absolu: {audio_path}")
        print(f"  - Fichier existe: {os.path.exists(audio_path)}")
        print(f"  - Taille: {os.path.getsize(audio_path) if os.path.exists(audio_path) else 'N/A'} bytes")
        
        if not os.path.exists(audio_path):
            print(f"[AUDIO] ❌ Le fichier n'existe pas!")
            return
        
        # ===== ÉTAPE 2 : NETTOYAGE CONNEXIONS EXISTANTES =====
        print(f"\n[AUDIO] 📋 ÉTAPE 2: Nettoyage des connexions existantes")
        print("-" * 60)
        print(f"[AUDIO] Nombre de voice_clients actuels: {len(bot.voice_clients)}")
        
        for i, vc in enumerate(bot.voice_clients):
            print(f"  [{i}] Guild: {vc.guild.name}, Connecté: {vc.is_connected()}")
            if vc.guild == ctx.guild:
                print(f"      → Déconnexion de {vc.guild.name}...")
                try:
                    await vc.disconnect(force=True)
                    print(f"      ✅ Déconnecté")
                except Exception as e:
                    print(f"      ❌ Erreur: {e}")
        
        await asyncio.sleep(1)
        print(f"[AUDIO] Attente de 1s complétée")
        
        # ===== ÉTAPE 3 : CONNEXION AU CANAL VOCAL =====
        print(f"\n[AUDIO] 📋 ÉTAPE 3: Connexion au canal vocal")
        print("-" * 60)
        print(f"[AUDIO] Tentative de connexion à '{voice_channel.name}'...")
        
        try:
            voice_client = await voice_channel.connect(timeout=60, reconnect=False)
            print(f"[AUDIO] ✅ Connecté au canal vocal")
            print(f"  - voice_client type: {type(voice_client)}")
            print(f"  - is_connected(): {voice_client.is_connected()}")
            print(f"  - Guild: {voice_client.guild.name}")
        except asyncio.TimeoutError as e:
            print(f"[AUDIO] ❌ Timeout lors de la connexion: {e}")
            traceback.print_exc()
            return
        except discord.errors.ClientException as e:
            print(f"[AUDIO] ❌ Erreur Discord: {e}")
            print(f"  - Type: {type(e)}")
            traceback.print_exc()
            return
        except IndexError as e:
            print(f"[AUDIO] ❌ IndexError lors de la connexion: {e}")
            print(f"  - Cela peut être un problème d'intents Discord")
            traceback.print_exc()
            return
        except Exception as e:
            print(f"[AUDIO] ❌ Erreur inattendue: {type(e).__name__}: {e}")
            traceback.print_exc()
            return
        
        await asyncio.sleep(0.5)
        
        # ===== ÉTAPE 4 : CRÉATION DE L'AUDIO SOURCE =====
        print(f"\n[AUDIO] 📋 ÉTAPE 4: Création de l'audio source")
        print("-" * 60)
        
        try:
            print(f"[AUDIO] Création de FFmpegPCMAudio...")
            print(f"  - Fichier: {audio_path}")
            print(f"  - Executable: ffmpeg")
            
            audio_source = discord.FFmpegPCMAudio(audio_path)
            print(f"[AUDIO] ✅ Audio source créée")
            print(f"  - Type: {type(audio_source)}")
            
        except IndexError as e:
            print(f"[AUDIO] ❌ IndexError lors de la création: {e}")
            print(f"  - FFmpeg peut ne pas être trouvé ou accessible")
            print(f"  - Vérifiez que FFmpeg est dans le PATH")
            traceback.print_exc()
            return
        except FileNotFoundError as e:
            print(f"[AUDIO] ❌ Fichier non trouvé: {e}")
            traceback.print_exc()
            return
        except Exception as e:
            print(f"[AUDIO] ❌ Erreur: {type(e).__name__}: {e}")
            traceback.print_exc()
            return
        
        # ===== ÉTAPE 5 : LECTURE DU SON =====
        print(f"\n[AUDIO] 📋 ÉTAPE 5: Lecture du son")
        print("-" * 60)
        
        try:
            print(f"[AUDIO] Démarrage de la lecture...")
            voice_client.play(audio_source)
            print(f"[AUDIO] ✅ Lecture démarrée")
            
            # Attendre la fin avec timeout
            max_wait = 60
            elapsed = 0
            check_interval = 0.5
            
            print(f"[AUDIO] Attente de la fin de la lecture (max {max_wait}s)...")
            while voice_client.is_playing() and elapsed < max_wait:
                await asyncio.sleep(check_interval)
                elapsed += check_interval
                if elapsed % 5 < check_interval:  # Print tous les ~5s
                    print(f"[AUDIO] En cours... ({elapsed:.1f}s)")
            
            if elapsed >= max_wait:
                print(f"[AUDIO] ⚠️  Timeout atteint ({max_wait}s)")
            else:
                print(f"[AUDIO] ✅ Lecture terminée ({elapsed:.1f}s)")
            
            await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"[AUDIO] ❌ Erreur lors de la lecture: {type(e).__name__}: {e}")
            traceback.print_exc()
        
    except Exception as e:
        print(f"[AUDIO] ❌ Exception générale non gérée: {type(e).__name__}: {e}")
        traceback.print_exc()
        
    finally:
        # ===== ÉTAPE 6 : NETTOYAGE =====
        print(f"\n[AUDIO] 📋 ÉTAPE 6: Nettoyage et déconnexion")
        print("-" * 60)
        
        if voice_client is not None:
            print(f"[AUDIO] voice_client existe")
            print(f"  - is_connected(): {voice_client.is_connected()}")
            
            if voice_client.is_connected():
                try:
                    print(f"[AUDIO] Déconnexion...")
                    await voice_client.disconnect(force=True)
                    print(f"[AUDIO] ✅ Déconnecté")
                except Exception as e:
                    print(f"[AUDIO] ❌ Erreur déconnexion: {type(e).__name__}: {e}")
        else:
            print(f"[AUDIO] voice_client est None")
        
        print("\n" + "="*60)
        print("[AUDIO] 🔍 FIN DEBUG")
        print("="*60 + "\n")

@bot.event
async def on_ready():
    print(f'{bot.user} s\'est connecté à Discord!')

@bot.command(name='chaos')
async def chaos(ctx):
    """Génère un texte aléatoire avec Gemini et joue un son"""
    global last_prompt
    try:
        # Afficher que le bot est en train de traiter
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
        
        # Jouer le son après avoir envoyé le texte
        await play_audio(ctx, "kaamelott.mp3")
            
    except Exception as e:
        print(f"[ERROR] Exception complète: {type(e).__name__}: {e}")
        await ctx.send(f"❌ Erreur lors de la génération du texte: {str(e)}")


@bot.command(name='prompt')
async def prompt(ctx):
    """Affiche le dernier prompt qui a été envoyé à Gemini"""
    global last_prompt
    
    if last_prompt is None:
        await ctx.send("❌ Aucun prompt n'a été généré pour le moment. Utilise `!chaos` d'abord.")
    else:
        # Discord a une limite de 2000 caractères par message
        max_length = 1900
        
        if len(last_prompt) <= max_length:
            # Si c'est court, on envoie directement
            await ctx.send(f"🔮 **Dernier prompt envoyé:**\n```\n{last_prompt}\n```")
        else:
            # Si c'est trop long, on découpe en plusieurs messages
            await ctx.send("🔮 **Dernier prompt envoyé:** (en plusieurs parties)")
            
            # Découper le prompt en chunks
            chunks = [last_prompt[i:i + max_length] for i in range(0, len(last_prompt), max_length)]
            
            for i, chunk in enumerate(chunks, 1):
                await ctx.send(f"```\n{chunk}\n```")
                
            await ctx.send(f"✅ Prompt affiché en {len(chunks)} partie(s)")


# Lancer le bot
bot.run(DISCORD_TOKEN)