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
intents.voice_states = True  # Ajouter les voice_states
intents.guilds = True  # Ajouter les guilds
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
        # Vérifier que l'utilisateur est dans un canal vocal
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            print("[AUDIO] ❌ L'utilisateur n'est pas dans un canal vocal")
            return
        
        # Vérifier que le fichier audio existe
        if not os.path.exists(audio_file):
            print(f"[AUDIO] ❌ Le fichier `{audio_file}` n'existe pas!")
            return
        
        voice_channel = ctx.author.voice.channel
        
        # Nettoyer les anciennes connexions
        for vc in bot.voice_clients:
            if vc.guild == ctx.guild:
                try:
                    await vc.disconnect(force=True)
                except:
                    pass
        
        await asyncio.sleep(1)
        
        # Se connecter
        print(f"[AUDIO] Tentative de connexion à {voice_channel.name}...")
        try:
            voice_client = await voice_channel.connect(timeout=60, reconnect=False)
            print(f"[AUDIO] ✅ Connecté au canal vocal")
        except Exception as e:
            print(f"[AUDIO] ❌ Erreur connexion: {e}")
            return
        
        await asyncio.sleep(0.5)
        
        # Jouer le son avec chemin absolu
        audio_path = os.path.abspath(audio_file)
        print(f"[AUDIO] Chemin absolu: {audio_path}")
        print(f"[AUDIO] Fichier existe: {os.path.exists(audio_path)}")
        
        try:
            print(f"[AUDIO] Création de l'audio source...")
            # Utiliser avant_options pour FFmpeg
            audio_source = discord.FFmpegPCMAudio(
                audio_path,
                executable="ffmpeg"
            )
            print(f"[AUDIO] Audio source créée, lecture en cours...")
            voice_client.play(audio_source)
            
            # Attendre la fin avec timeout
            max_wait = 60  # 60 secondes max
            elapsed = 0
            while voice_client.is_playing() and elapsed < max_wait:
                await asyncio.sleep(0.1)
                elapsed += 0.1
            
            print(f"[AUDIO] ✅ Lecture terminée")
            await asyncio.sleep(0.5)
            
        except IndexError as e:
            print(f"[AUDIO] ❌ Erreur IndexError (probablement FFmpeg): {e}")
            print(f"[AUDIO] Vérifiez que FFmpeg est correctement installé")
        except Exception as e:
            print(f"[AUDIO] ❌ Erreur lors de la lecture: {type(e).__name__}: {e}")
        
    except Exception as e:
        print(f"[AUDIO] ❌ Exception générale: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Toujours déconnecter à la fin
        if voice_client is not None and voice_client.is_connected():
            try:
                print("[AUDIO] Déconnexion...")
                await voice_client.disconnect(force=True)
                print("[AUDIO] ✅ Déconnecté")
            except Exception as e:
                print(f"[AUDIO] Erreur déconnexion: {e}")

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