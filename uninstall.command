#!/bin/bash
# =============================================================================
#  VoixFlash — Désinstallateur (à double-cliquer)
#  Arrête l'application, retire le démarrage automatique et supprime ses fichiers.
#  (Pense aussi à retirer "Python"/VoixFlash des réglages de confidentialité.)
# =============================================================================
APP_NAME="VoixFlash"
APP_DIR="$HOME/Library/Application Support/$APP_NAME"
PLIST="$HOME/Library/LaunchAgents/com.voixflash.agent.plist"

echo "Désinstallation de $APP_NAME…"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
rm -rf "$APP_DIR"

echo "• Application arrêtée et fichiers supprimés."
echo "• Tes transcriptions enregistrées en .txt restent dans :"
echo "    ~/Documents/$APP_NAME Transcriptions"
echo "• Le modèle téléchargé reste en cache dans ~/.cache/huggingface (supprime-le si tu veux)."
echo ""
read -n 1 -s -r -p "Appuie sur une touche pour fermer."
echo ""
