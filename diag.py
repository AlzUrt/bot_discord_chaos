import discord
import sys
import subprocess

print("=" * 60)
print("🔍 VÉRIFICATION DE DISCORD.PY")
print("=" * 60)

print(f"\n📦 Version de discord.py: {discord.__version__}")
print(f"🐍 Version de Python: {sys.version}")

# Vérifier si c'est une version compatible
version_parts = discord.__version__.split('.')
major = int(version_parts[0])

if major >= 2:
    print("\n✅ Vous avez discord.py 2.x (compatible)")
else:
    print("\n⚠️ Vous avez une version ancienne de discord.py")
    print("📝 Recommendation: Mettez à jour avec:")
    print("   pip install --upgrade discord.py")

# Vérifier les problèmes courants
print("\n" + "=" * 60)
print("🔧 VÉRIFICATION DES DÉPENDANCES AUDIO")
print("=" * 60)

try:
    import nacl
    print(f"✅ PyNaCl installé (version {nacl.__version__})")
except ImportError:
    print("❌ PyNaCl manquant - REQUIS pour l'audio")
    print("   Installez avec: pip install PyNaCl")

try:
    # Vérifier FFmpeg
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
    if result.returncode == 0:
        print("✅ FFmpeg installé et accessible")
    else:
        print("⚠️ FFmpeg trouvé mais erreur à l'exécution")
except FileNotFoundError:
    print("❌ FFmpeg introuvable")
    print("   Installez depuis: https://ffmpeg.org/download.html")
except Exception as e:
    print(f"❌ Erreur vérification FFmpeg: {e}")

print("\n" + "=" * 60)
print("💡 CONSEIL: Si vous avez toujours des erreurs 4006")
print("=" * 60)
print("""
1. Vérifiez votre connexion Internet
2. Vérifiez que votre pare-feu n'interfère pas
3. Essayez de désactiver le VPN si vous en utilisez un
4. Redémarrez le bot et Discord
5. Vérifiez que votre bot a les bonnes permissions
6. Essayez une autre région Discord (voice channel)
""")