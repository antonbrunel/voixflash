# VoixFlash 🎙️

**Dictée vocale gratuite et 100 % hors-ligne pour Mac (Apple Silicon).**
Parle au lieu de taper : une touche pour dicter **partout**, un bouton pour les **réunions**.
Aucun compte, aucun abonnement, aucune clé. Ta voix ne quitte jamais ton Mac.

> 🇬🇧 *Free, fully offline French/English dictation tool for Apple Silicon Macs, living in the
> menu bar. Powered by faster-whisper (CPU only). No account, no subscription, no cloud.*

---

## ✨ Ce que ça fait

- **Dictée éclair, partout** : place ton curseur dans n'importe quel champ, maintiens une
  touche, parle, relâche → le texte s'écrit tout seul à l'endroit du curseur.
- **Mode réunion** : enregistre aussi longtemps que tu veux ; le texte complet s'affiche dans
  l'app et s'exporte en `.txt` daté.
- **Import d'un fichier audio/vidéo** : transcris un fichier existant (mp3, m4a, wav, flac,
  ogg… ou la piste audio d'un mp4/mov). Découpage automatique, progression dans le menu,
  annulable — tient des fichiers de **2 h et plus** sans saturer la mémoire ni le Mac.
- **Hors-ligne et privé** : moteur [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  sur **CPU uniquement**, rien n'est envoyé sur internet.
- **Léger et discret** : vit dans la barre des menus, quasi invisible au repos.
- **Accents français impeccables** : collage via le presse-papiers (jamais lettre par lettre).
- **Séparation des locuteurs** (réunions) : option à activer d'un clic — affiche « — Locuteur 1 :
  … », « — Locuteur 2 : … ». Télécharge un petit module local une seule fois (~50 Mo, depuis
  GitHub, **sans compte ni clé**) ; tout reste sur ton Mac.
- **Historique** local (dictées + réunions), copiable et exportable, avec **recherche plein-texte**
  (mots-clés, accents ignorés).
- **Réglages simples** : qualité/vitesse, langue (FR/EN), touche de dictée.
- **Vocabulaire personnalisé** : tes noms propres et ton jargon écrits correctement, sans
  intelligence artificielle supplémentaire ni ralentissement.

Un **mode d'emploi complet** est intégré : icône VoixFlash › **Aide & autorisations › Mode d'emploi complet**.

---

## ✅ Prérequis

- Un **Mac Apple Silicon** (puce M1/M2/M3/M4).
- **macOS** récent.
- Une connexion internet **uniquement à l'installation** (pour télécharger l'outil et le
  modèle de transcription). Ensuite, tout fonctionne hors-ligne.

---

## 📦 Installation

1. **Télécharge** le projet :
   - bouton vert **« Code » › « Download ZIP »** sur GitHub, **ou** la dernière archive dans
     [**Releases**](../../releases) ;
   - décompresse-le.
2. Garde **`install.command`** et **`voixflash.py`** dans le **même dossier**.
3. **Double-clique sur `install.command`.** Il prépare tout automatiquement (Python isolé,
   bibliothèques, modèle, démarrage à la session). Compte quelques minutes la première fois.
4. Quand c'est fini, l'icône **micro** apparaît en haut à droite, dans la barre des menus.

> L'installateur n'installe **rien dans le système** : tout vit dans
> `~/Library/Application Support/VoixFlash/`. La désinstallation est propre (voir plus bas).

---

## 🔓 Premier lancement (important — app non signée)

VoixFlash est **gratuit et non signé** (pas encore de certificat Apple payant). macOS va donc
afficher un avertissement **la première fois seulement**. C'est normal pour un outil libre.

- **Si `install.command` refuse de s'ouvrir** (« développeur non identifié ») :
  **clic droit** sur le fichier › **Ouvrir** › **Ouvrir**.
- **Si macOS bloque encore** : va dans **Réglages Système › Confidentialité et sécurité**,
  descends tout en bas, et clique **« Ouvrir quand même »**, puis relance.

---

## 🔐 Autorisations (à accorder une fois)

macOS protège le micro et le clavier. Après l'installation, clique l'icône VoixFlash ›
**« Aide & autorisations »**, puis suis les boutons :

1. **Microphone** — pour entendre ta voix.
2. **Accessibilité** — pour coller le texte (Cmd+V).
3. **Surveillance des entrées** — pour la touche de dictée.

Puis clique **« Redémarrer VoixFlash »**.

> Dans les listes de macOS, l'entrée à activer apparaît sous le nom **« Python »** (c'est
> normal tant que l'app n'est pas notarisée). Le menu **Aide › « Voir le chemin à autoriser »**
> donne le fichier exact si besoin.

---

## 🗣️ Utilisation

- **Dictée éclair** : maintiens la touche (par défaut **Option droite**), parle, relâche.
- **Réunion** : icône › **« Démarrer une réunion »** … **« Arrêter la réunion »**.
- **Importer un fichier audio** : icône › **Réunions › « Importer un fichier audio… »** →
  choisis un fichier audio ou vidéo. La langue est détectée automatiquement, la progression
  s'affiche dans le menu, et l'item devient **« Annuler la transcription en cours »** si tu
  veux l'arrêter (le texte déjà transcrit est gardé).
- **Indicateur** (barre des menus) : micro fin = chargement · micro plein = prêt · pastille
  d'enregistrement = enregistre · forme d'onde = transcrit · presse-papiers = écrit le texte.

Tout le reste (comportement du presse-papiers, limites, historique…) est détaillé dans le
**Mode d'emploi complet** intégré à l'app.

### Import audio — formats, performances et limites

- **Formats** : mp3, m4a/aac, wav, aiff, caf, flac, ogg/opus… et la **piste audio des
  vidéos** (mp4, mov, m4v, mkv, webm). Aucun ffmpeg à installer (décodage intégré).
- **Performances** : tout se fait sur le **CPU**. Ordre de grandeur selon la qualité : *small*
  (défaut) ≈ **1 h d'audio transcrite en ~15 min** ; *medium* nettement plus lent. L'opération
  tourne en arrière-plan, avec le nombre de cœurs **bridé** pour garder le Mac réactif.
- **Durée / mémoire** : les fichiers sont **découpés en blocs** et décodés en flux → la
  mémoire reste stable même sur **2 h et plus**. Au-delà de 30 min, une estimation du temps
  est proposée avant de lancer ; au-delà de 3 h, une confirmation est demandée.
- **Limites** : pas de séparation des locuteurs (texte continu) ; fichiers **protégés (DRM)**
  refusés ; une seule transcription à la fois (import, réunion ou dictée).

---

## ⚙️ Réglages (menu de l'icône)

| Réglage | Détail |
|---|---|
| **Qualité / vitesse** | Rapide (tiny) → Très précis (medium). Défaut : **Précis (small)**. Le **1er choix** d'une qualité télécharge le modèle une fois (jusqu'à ~1 min ; un message le signale), puis c'est hors-ligne. |
| **Langue** | **Français** (défaut), **Anglais**, ou **Automatique** (détecte la langue à chaque dictée — idéal pour alterner FR/EN). |
| **Touche de dictée** | Préréglages (Option droite par défaut, Cmd droite, Ctrl droite, F5) **ou « Choisir ma touche… »** : appuie sur la touche que tu veux, elle est captée telle quelle (fiable quel que soit le clavier). |
| **Réunions › Importer un fichier audio…** | Transcrit un fichier audio/vidéo existant comme une réunion (langue auto, découpage automatique, progression + annulation). |
| **Réunions › Horodatage** | Ajoute `[mm:ss]` devant chaque passage (réunions **et** imports). |
| **Texte dicté › Vocabulaire** | Ajoute les noms propres, marques et termes métier tels que tu veux les voir. Les variantes approchantes sont corrigées, même quand le moteur découpe le mot (*voie flash* → *VoixFlash*). Corrections exactes possibles, utilisables aussi comme raccourcis de saisie. |
| **Texte dicté › Retirer les hésitations** | Efface les « euh » et « hmm » du texte (activé). |
| **Restaurer le presse-papiers** | Remet ton ancien presse-papiers après une dictée (activé), avec toutes ses données (image, texte enrichi, fichiers). |

---

## 📁 Où sont mes fichiers ?

- Réglages, historique, journal : `~/Library/Application Support/VoixFlash/`
- Transcriptions exportées (`.txt` datés) : `~/Documents/VoixFlash Transcriptions/`

---

## 🧹 Désinstallation

Double-clique sur **`uninstall.command`**. L'app s'arrête, le démarrage automatique est retiré
et ses fichiers sont supprimés. Tes transcriptions `.txt` déjà exportées sont conservées.

---

## 🛠️ Dépannage

- **Rien ne s'écrit en dictée éclair** → vérifie **Accessibilité** *et* **Surveillance des
  entrées**, puis **Redémarrer VoixFlash**.
- **Pas de son capté** → vérifie **Microphone**.
- **Je ne vois pas l'icône** → sur un MacBook, elle peut se cacher derrière l'encoche ; réduis
  le nombre d'icônes de la barre.
- **« Ce fichier ne contient pas de piste audio lisible »** → format non reconnu, fichier
  corrompu ou **protégé (DRM)**. Convertis-le d'abord en mp3/m4a/wav.
- **Import très lent** → choisis une qualité plus rapide (*small*/*base*/*tiny*) dans
  **Qualité / vitesse** ; tu peux annuler depuis le menu sans perdre le texte déjà transcrit.
- **Journal technique** : `~/Library/Application Support/VoixFlash/voixflash.log`

---

## 🔒 Vie privée

Tout est **local**. Après l'installation, aucune donnée audio ni texte ne sort de ton Mac.
Aucun compte, aucune télémétrie.

---

## 👩‍💻 Pour les curieux / développeurs

- Application en **Python** : `voixflash.py` (barre des menus via `rumps`, écoute clavier via
  `pynput`, audio via `sounddevice`, transcription via `faster-whisper` en `int8` sur CPU).
- L'installateur utilise [`uv`](https://github.com/astral-sh/uv) pour créer un environnement
  **Python 3.12** isolé (le Python système récent n'a pas encore de bibliothèques compatibles).
- Historique stocké en **SQLite** local.

```
install.command       Installateur tout-en-un (à double-cliquer)
uninstall.command     Désinstallateur
voixflash.py          L'application complète, commentée
build-release.command Fabrique l'archive .zip à partager
LISEZ-MOI.md          Guide rapide (inclus dans le .zip)
```

---

## 📄 Licence

Code de VoixFlash : **MIT** (voir [LICENSE](LICENSE)).

Bibliothèques tierces (chacune sous sa propre licence) : faster-whisper & CTranslate2 (MIT),
rumps (BSD), sounddevice & NumPy (BSD/MIT), pyobjc (MIT), **pynput (LGPL-3.0)**. VoixFlash les
utilise telles quelles, sans les modifier.

---

*VoixFlash est un outil libre fourni « tel quel », sans garantie. Il n'est pas affilié à Apple.*
