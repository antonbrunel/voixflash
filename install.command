#!/bin/bash
# =============================================================================
#  VoixFlash — Installateur tout-en-un (à double-cliquer)
#  Prépare automatiquement : environnement Python 3.12 compatible, bibliothèques,
#  téléchargement du modèle de transcription, et démarrage automatique à la session.
#  Aucune commande à taper.
# =============================================================================
set -e
set -o pipefail   # sans ça, un échec de curl dans « curl … | sh » passerait inaperçu

APP_NAME="VoixFlash"
APP_DIR="$HOME/Library/Application Support/$APP_NAME"
VENV="$APP_DIR/venv"
PLIST="$HOME/Library/LaunchAgents/com.voixflash.agent.plist"
LABEL="com.voixflash.agent"

# Dossier où se trouve ce script (et voixflash.py, juste à côté).
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_SRC="$HERE/voixflash.py"
LOG="$APP_DIR/voixflash.log"

# Petit indicateur animé pendant une opération longue (sinon l'écran semble figé).
# Argument : le PID à surveiller. S'arrête dès que ce processus se termine.
spin() {
  local pid="$1"
  local sp='|/-\'
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$(( (i + 1) % 4 ))
    printf "\r   [%s] Téléchargement en cours… (plusieurs minutes possibles, c'est normal)" "${sp:$i:1}"
    sleep 0.2
  done
  printf "\r\033[K"   # efface la ligne de l'indicateur
}

# Filet de sécurité : si une commande échoue (réseau coupé, paquet indisponible…),
# `set -e` arrête le script. Sans ce piège, la fenêtre se fermerait sur une erreur
# anglaise cryptique. On affiche plutôt un message clair + une pause. Les chemins
# d'échec déjà gérés posent HANDLED=1 pour ne pas afficher ce message deux fois.
HANDLED=0
on_exit() {
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$HANDLED" -ne 1 ]; then
    echo ""
    echo "==================================================================="
    echo "   ⚠️  L'installation s'est interrompue (code $rc)."
    echo "==================================================================="
    echo ""
    echo "Le plus souvent : connexion internet coupée ou instable pendant un"
    echo "téléchargement. Vérifie ta connexion, puis double-clique de nouveau"
    echo "sur install.command."
    [ -f "$LOG" ] && echo "" && echo "Journal éventuel : $LOG"
    echo ""
    read -n 1 -s -r -p "Appuie sur une touche pour fermer cette fenêtre."
    echo ""
  fi
}
trap on_exit EXIT

echo ""
echo "==================================================================="
echo "   Installation de $APP_NAME"
echo "==================================================================="
echo ""

# --- 0. Vérifier la présence du code source -----------------------------------
if [ ! -f "$SCRIPT_SRC" ]; then
  HANDLED=1
  echo "ERREUR : le fichier voixflash.py est introuvable à côté de l'installateur."
  echo "Garde install.command et voixflash.py dans le même dossier."
  read -n 1 -s -r -p "Appuie sur une touche pour fermer."
  exit 1
fi

# --- 1. Dossier de l'application ----------------------------------------------
mkdir -p "$APP_DIR"
cp "$SCRIPT_SRC" "$APP_DIR/voixflash.py"
echo "• Code copié dans : $APP_DIR"

# --- 2. Outil de gestion Python (uv) ------------------------------------------
# uv télécharge un Python 3.12 propre et installe les bibliothèques de façon fiable.
if ! command -v uv >/dev/null 2>&1; then
  echo "• Installation de l'outil 'uv' (une seule fois)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Rendre uv accessible immédiatement dans ce script.
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ ! -x "$UV" ] && ! command -v uv >/dev/null 2>&1; then
  HANDLED=1
  echo ""
  echo "Impossible d'installer l'outil « uv » (téléchargement échoué)."
  echo "Vérifie ta connexion internet, puis double-clique de nouveau sur install.command."
  read -n 1 -s -r -p "Appuie sur une touche pour fermer."
  echo ""
  exit 1
fi
echo "• uv : $("$UV" --version 2>/dev/null || echo introuvable)"

# --- 3. Environnement Python 3.12 + bibliothèques -----------------------------
# On vise Python 3.12 : c'est la version la mieux supportée par les bibliothèques de
# transcription (le Python 3.14 du système n'a pas encore de versions compilées).
echo "• Création de l'environnement Python 3.12 (téléchargé si nécessaire)…"
"$UV" python install 3.12
PYBASE="$("$UV" python find 3.12 2>/dev/null || true)"

# On crée le venv à partir du binaire Python RÉSOLU à sa version exacte (dossier
# « cpython-3.12.X »), que 'uv' ne déplace jamais — une mise à jour crée un nouveau
# dossier sans toucher l'ancien. Ainsi les autorisations de sécurité du Mac (micro,
# accessibilité, surveillance des entrées) restent attachées à un binaire qui ne
# bouge pas, même si 'uv' évolue. Repli sur 'uv venv' si quoi que ce soit échoue.
# Réutiliser le venv EXISTANT s'il fonctionne. C'est crucial : macOS attache les
# autorisations (micro, accessibilité, surveillance des entrées) au binaire Python.
# Recréer le venv à chaque réinstallation le ferait pointer vers un nouveau binaire
# (si 'uv' a livré un Python 3.12.x plus récent) → toutes les autorisations seraient
# silencieusement perdues. On ne le (re)crée donc que s'il est absent ou cassé.
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'pass' 2>/dev/null; then
  echo "  • environnement Python existant réutilisé (autorisations préservées)"
else
  PYREAL=""
  if [ -n "$PYBASE" ]; then
    BINDIR="$(cd "$(dirname "$PYBASE")" && pwd -P)"
    PYREAL="$BINDIR/$(basename "$PYBASE")"
  fi
  if [ -n "$PYREAL" ] && "$PYREAL" -m venv --without-pip "$VENV" 2>/dev/null && [ -x "$VENV/bin/python" ]; then
    echo "  • environnement créé (identité stable pour les autorisations)"
  else
    echo "  • repli : environnement 'uv venv'"
    "$UV" venv --python 3.12 "$VENV"
  fi
fi

echo "• Installation des bibliothèques (transcription, audio, clavier, barre des menus)…"
"$UV" pip install --python "$VENV/bin/python" \
  rumps \
  pynput \
  sounddevice \
  numpy \
  faster-whisper \
  pyobjc-framework-Cocoa \
  pyobjc-framework-Quartz \
  pyobjc-framework-ApplicationServices

# --- 4. Pré-téléchargement du modèle (pour fonctionner ensuite hors-ligne) -----
# On télécharge le modèle réellement configuré (config.json peut exister d'une
# précédente installation et viser autre chose que « small »), sinon « small ».
MODEL="small"
if [ -f "$APP_DIR/config.json" ]; then
  MODEL_CFG="$("$VENV/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("model","small"))' "$APP_DIR/config.json" 2>/dev/null || echo small)"
  [ -n "$MODEL_CFG" ] && MODEL="$MODEL_CFG"
fi
echo "• Téléchargement du modèle de transcription « $MODEL » (une seule fois)."
echo "  ⏳ À la première installation, cela peut prendre plusieurs MINUTES selon ta"
echo "     connexion. C'est NORMAL — ne ferme pas cette fenêtre tant que ça tourne."
DL_LOG="$(mktemp)"
# Le téléchargement tourne en arrière-plan ; on anime un indicateur pour montrer que
# l'installation n'est pas figée. La sortie (dont l'avertissement HF_TOKEN, sans
# gravité) est mise de côté et n'est ré-affichée qu'en cas d'échec.
(
  MODEL="$MODEL" "$VENV/bin/python" - <<'PY'
import os
from faster_whisper import WhisperModel
WhisperModel(os.environ.get("MODEL", "small"), device="cpu", compute_type="int8")
print("Modèle prêt.")
PY
) >"$DL_LOG" 2>&1 &
DL_PID=$!
spin "$DL_PID"
DL_OK=1
if wait "$DL_PID"; then
  echo "  ✓ Modèle « $MODEL » prêt — la transcription fonctionnera désormais hors-ligne."
else
  DL_OK=0
  echo "  ⚠ Téléchargement non terminé : il sera repris au 1er usage (internet requis cette fois-là)."
  # On montre les erreurs utiles, mais on masque l'avertissement HF_TOKEN (sans gravité).
  # « || true » : pipefail ne doit pas faire échouer l'install si grep ne trouve rien.
  grep -v -e "HF_TOKEN" -e "unauthenticated requests" "$DL_LOG" 2>/dev/null | tail -n 6 | sed 's/^/      /' || true
fi
rm -f "$DL_LOG"

# --- 5. Démarrage automatique à l'ouverture de session (LaunchAgent) -----------
echo "• Configuration du démarrage automatique…"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV/bin/python</string>
        <string>$APP_DIR/voixflash.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>LANG</key>
        <string>en_US.UTF-8</string>
        <key>LC_CTYPE</key>
        <string>en_US.UTF-8</string>
    </dict>
    <key>StandardOutPath</key>
    <string>$APP_DIR/voixflash.log</string>
    <key>StandardErrorPath</key>
    <string>$APP_DIR/voixflash.log</string>
</dict>
</plist>
PLISTEOF

# (Re)chargement de l'agent : il démarre maintenant et à chaque session.
# On note la taille du journal AVANT le démarrage pour ne lire que les lignes neuves.
LOG_LINES_BEFORE="$(wc -l < "$LOG" 2>/dev/null || echo 0)"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

# --- 6. Vérification RÉELLE que l'application a démarré ------------------------
# On ne se contente plus d'annoncer « terminé » : on laisse l'app démarrer, puis on
# vérifie qu'elle tourne toujours et qu'aucune erreur fatale n'est apparue.
echo "• Vérification du démarrage de l'application…"
sleep 3
NEW_LOG="$(tail -n +"$((LOG_LINES_BEFORE + 1))" "$LOG" 2>/dev/null || true)"
APP_OK=1
if printf '%s' "$NEW_LOG" | grep -q "Traceback"; then
  APP_OK=0
elif ! launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -q "state = running"; then
  APP_OK=0
fi

echo ""
if [ "$APP_OK" -ne 1 ]; then
  echo "==================================================================="
  echo "   ⚠️  L'application n'a PAS démarré correctement."
  echo "==================================================================="
  echo ""
  echo "Voici la fin du journal d'erreurs (utile pour corriger) :"
  echo "-------------------------------------------------------------------"
  printf '%s\n' "$NEW_LOG" | tail -n 20 | sed 's/^/  /'
  echo "-------------------------------------------------------------------"
  echo ""
  echo "Journal complet : $LOG"
  echo "Une fois le souci corrigé, double-clique de nouveau sur install.command."
  echo ""
  HANDLED=1
  read -n 1 -s -r -p "Appuie sur une touche pour fermer cette fenêtre."
  echo ""
  exit 1
fi

echo "==================================================================="
echo "   ✅ Installation terminée — l'application tourne."
echo "==================================================================="
echo ""
# État du modèle : honnête. S'il n'a pas pu être préparé (téléchargement échoué, ou
# erreur de chargement détectée dans le journal), la 1re dictée aura besoin d'internet.
if [ "$DL_OK" -ne 1 ] || printf '%s' "$NEW_LOG" | grep -q "Erreur de chargement"; then
  echo "⚠ Le modèle « $MODEL » n'a pas encore pu être préparé : la TOUTE PREMIÈRE"
  echo "  dictée nécessitera une connexion internet (téléchargement automatique),"
  echo "  puis tout fonctionnera hors-ligne. Tu peux aussi relancer install.command."
  echo ""
fi
echo "OÙ EST L'ICÔNE ?"
echo "  En haut à DROITE de l'écran, dans la barre des menus, une petite icône"
echo "  de MICRO blanche 🎙️  apparaît (micro fin pendant le chargement, puis"
echo "  micro plein quand c'est prêt). Pas d'emoji coloré : du blanc, comme les"
echo "  autres icônes système."
echo ""
echo "  Tu ne la vois pas ?"
echo "   • Sur un MacBook à ENCOCHE, s'il y a beaucoup d'icônes, certaines se"
echo "     cachent derrière l'encoche. Enlève quelques icônes voisines (Cmd+glisser"
echo "     hors de la barre) ou utilise un gestionnaire de barre des menus."
echo "   • Sinon, regarde le journal : $LOG"
echo ""
echo "DERNIÈRE ÉTAPE — autoriser le micro et le clavier :"
echo "  Clique sur l'icône VoixFlash › « Aide & autorisations » et suis les"
echo "  3 boutons (Microphone, Accessibilité, Surveillance des entrées),"
echo "  puis clique « Redémarrer VoixFlash »."
echo ""
read -n 1 -s -r -p "Appuie sur une touche pour fermer cette fenêtre."
echo ""
