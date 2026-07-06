# VoixFlash 🎙️ — Dictée vocale gratuite et hors-ligne pour Mac

Parle au lieu de taper. Une touche pour dicter partout, un bouton pour les réunions.
100 % gratuit, 100 % hors-ligne (moteur **faster-whisper**), aucune connexion ni
compte requis. Discret dans la barre des menus, quasi invisible au repos.

> Un **mode d'emploi complet** est intégré à l'app : icône VoixFlash ›
> **Aide & autorisations › Mode d'emploi complet**.

---

## 1. Installation (un seul fichier)

1. Garde les deux fichiers **dans le même dossier** : `install.command` et `voixflash.py`.
2. **Double-clique sur `install.command`.**
   - S'il refuse de s'ouvrir (« développeur non identifié »), fais un **clic droit ›
     Ouvrir › Ouvrir**. Si macOS bloque encore : **Réglages Système › Confidentialité et
     sécurité**, tout en bas, **« Ouvrir quand même »**.
   - Une fenêtre Terminal s'ouvre et prépare tout automatiquement (Python isolé,
     bibliothèques, modèle, démarrage automatique). Laisse-la travailler quelques minutes.
3. À la fin, l'icône **micro** (en blanc) apparaît en haut à droite, dans la barre des menus.

> L'installation a besoin d'internet **une seule fois** (pour télécharger le modèle).
> Ensuite, tout fonctionne hors-ligne.

---

## 2. Autoriser le micro et le clavier (obligatoire, à faire une fois)

macOS protège le micro et le clavier. Il faut autoriser VoixFlash **3 fois**.
Le plus simple : clique sur l'icône VoixFlash dans la barre des menus ›
**« Aide & autorisations »**, puis suis les boutons.

### Étapes détaillées

1. Clique l'icône VoixFlash › **Aide & autorisations › Ouvrir réglages › Microphone**.
   Active l'interrupteur (l'entrée s'appelle **« Python »**).
2. Reviens au menu › **Ouvrir réglages › Accessibilité**. Active l'interrupteur.
   *(C'est ce qui autorise le collage du texte avec Cmd+V.)*
3. Reviens au menu › **Ouvrir réglages › Surveillance des entrées**. Active l'interrupteur.
   *(C'est ce qui autorise la touche de dictée.)*
4. Clique l'icône VoixFlash › **« Redémarrer VoixFlash »** pour que tout soit pris en compte.

> Astuce : si tu ne vois pas l'entrée dans une liste, clique sur **+** et ajoute le programme
> dont le chemin est affiché par « Aide & autorisations › Voir le chemin à autoriser ».
> La première fois, macOS peut aussi afficher tout seul la demande de Microphone : clique **Autoriser**.

---

## 3. Utilisation

### Dictée éclair (partout)
1. Place le curseur dans n'importe quel champ de texte (mail, navigateur, note…).
2. **Maintiens la touche de dictée** (par défaut **Option droite**), parle, puis **relâche**.
3. Le texte s'écrit tout seul à l'endroit du curseur.

### Réunion / enregistrement long
1. Clique l'icône VoixFlash › **« Démarrer une réunion »**.
2. Parle aussi longtemps que tu veux (l'icône montre l'état « enregistre » : le micro tourne).
3. Clique **« Arrêter la réunion »**. Le texte complet s'affiche dans une fenêtre, où tu peux
   le lire, le modifier, le **Copier** ou le **Supprimer**.
4. Pour le garder en fichier : menu › **Réunions › « Exporter la dernière réunion (.txt) »**
   → un fichier daté est créé dans `~/Documents/VoixFlash Transcriptions`.

> En réunion, le presse-papiers n'est **pas** touché tout seul (copie via le bouton).
> En dictée éclair, ton presse-papiers est préservé (si du texte) puis remis en place.

### Importer un fichier audio (ou vidéo)
1. Menu › **Réunions › « Importer un fichier audio… »**, puis choisis ton fichier
   (mp3, m4a, wav, flac, ogg, aiff… ou une vidéo mp4/mov — seule la piste audio est lue).
2. VoixFlash le transcrit **comme une réunion** : le texte s'affiche dans une fenêtre et
   s'ajoute à l'historique. La **langue est détectée automatiquement**.
3. Ça tourne **en arrière-plan** : la progression s'affiche dans le menu
   (« Transcription du fichier… NN % »). Tu peux **annuler** à tout moment (l'item devient
   « Annuler la transcription en cours ») sans perdre le texte déjà obtenu.

> Tout se fait sur le processeur : compte ~15 min pour 1 h d'audio en qualité « small »
> (plus lent en « medium »). Les fichiers longs (**2 h et plus**) sont découpés tout seuls,
> donc la mémoire reste stable. La séparation des locuteurs ne concerne **que les réunions
> enregistrées en direct** (voir Réglages), pas l'import ; fichiers protégés (DRM) refusés.

### Indicateur d'état (barre des menus)
L'icône (un micro blanc) change de **forme** : micro fin = chargement · micro plein = prêt ·
pastille d'enregistrement = enregistre · forme d'onde = transcrit · presse-papiers = écrit le texte.

### Historique
- Toutes les transcriptions (dictées, réunions **et imports de fichiers**) s'ajoutent au menu
  **« Historique récent »**. **Clique une entrée** pour la rouvrir (lire, modifier, copier, supprimer).
- **Rechercher** : **Historique récent › 🔍 Rechercher…** — tape un ou plusieurs mots-clés
  (accents et majuscules ignorés) ; les correspondances apparaissent dans **« Résultats de
  recherche »**, cliquables.
- **Réunions › Exporter…** et **Exporter tout l'historique (.txt)** créent des fichiers datés.

---

## 4. Réglages (menu de l'icône)

- **Qualité / vitesse** : *Rapide (tiny)* → *Très précis (medium)*. Défaut : **Précis (small)**.
- **Langue** : **Français** (défaut), **Anglais**, ou **Automatique** (détecte la langue
  à chaque dictée — pratique pour alterner FR/EN).
- **Touche de dictée** : préréglages (Option droite par défaut…) ou **« Choisir ma touche… »**
  qui capte la touche que tu presses (fiable quel que soit le clavier).
- **Réunions › Importer un fichier audio…** : transcrit un fichier audio/vidéo existant
  (langue auto, découpage automatique, progression, annulable).
- **Réunions › Horodatage des passages** : ajoute `[mm:ss]` devant chaque passage (réunions et imports).
- **Réunions › Séparer les locuteurs** : affiche « — Locuteur 1 : … », « — Locuteur 2 : … »
  dans tes réunions. La **1re activation** télécharge un petit module (~50 Mo, depuis GitHub,
  **sans compte ni clé**) ; ensuite tout est hors-ligne. **Réunions › Locuteurs attendus** :
  laisse **Automatique**, ou indique le nombre de personnes (plus fiable). La séparation
  fonctionne bien sur des voix distinctes et se dégrade quand plusieurs parlent en même temps.
- **Restaurer le presse-papiers après une dictée** : remet ton ancien presse-papiers (activé).

> Le **1er choix** d'une qualité télécharge le modèle une fois (jusqu'à ~1 min pour
> *medium*, ~1,5 Go ; un message le signale). L'icône micro se remplit quand c'est prêt.
> Ensuite, tout est hors-ligne.

---

## 5. Désinstallation

Double-clique sur **`uninstall.command`**. Cela arrête l'app, retire le démarrage
automatique et supprime ses fichiers. Tes transcriptions `.txt` déjà exportées sont
conservées dans `~/Documents/VoixFlash Transcriptions`.

---

## En cas de souci

- Rien ne s'écrit en dictée éclair → vérifie **Accessibilité** *et* **Surveillance des
  entrées**, puis **Redémarrer VoixFlash**.
- Pas de son capté → vérifie **Microphone**.
- L'icône est introuvable → sur un MacBook, elle peut se cacher derrière l'encoche.
- Journal technique : `~/Library/Application Support/VoixFlash/voixflash.log`.
