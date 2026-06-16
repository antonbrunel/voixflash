#!/bin/bash
# =============================================================================
#  VoixFlash — Fabrique l'archive .zip à partager (à double-cliquer)
#  Met dans VoixFlash.zip uniquement ce dont l'utilisateur final a besoin :
#  l'installateur, le désinstallateur, l'application et le guide rapide.
#  (Le code source de dev, les notes et les fichiers runtime ne sont PAS inclus.)
# =============================================================================
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

STAGE="VoixFlash"
OUT="VoixFlash.zip"

# Fichiers livrés à l'utilisateur final.
FILES=(install.command uninstall.command voixflash.py LISEZ-MOI.md)

echo "• Vérification des fichiers…"
for f in "${FILES[@]}"; do
  if [ ! -f "$HERE/$f" ]; then
    echo "ERREUR : fichier manquant : $f"
    read -n 1 -s -r -p "Appuie sur une touche pour fermer."
    exit 1
  fi
done

echo "• Préparation du dossier…"
rm -rf "$HERE/$STAGE" "$HERE/$OUT"
mkdir -p "$HERE/$STAGE"
cp "${FILES[@]}" "$HERE/$STAGE/"
# On s'assure que les scripts restent exécutables après décompression.
chmod +x "$HERE/$STAGE/install.command" "$HERE/$STAGE/uninstall.command"

echo "• Création de l'archive $OUT…"
# -X : pas d'attributs étendus macOS ; on exclut aussi les .DS_Store éventuels.
zip -r -X "$OUT" "$STAGE" -x "*.DS_Store" >/dev/null
rm -rf "$HERE/$STAGE"

echo ""
echo "✅ Archive prête : $HERE/$OUT"
echo "   → À déposer dans une Release GitHub, ou à envoyer telle quelle."
echo ""
read -n 1 -s -r -p "Appuie sur une touche pour fermer."
echo ""
