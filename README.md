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
- **Séparation des locuteurs** : option à activer d'un clic — affiche « — Locuteur 1 :
  … », « — Locuteur 2 : … », en réunion **et** sur les fichiers importés. Télécharge un petit
  module local une seule fois (~50 Mo, depuis GitHub, **sans compte ni clé**) ; tout reste sur
  ton Mac. Tu peux ensuite **nommer** les locuteurs, et en **fusionner** deux quand une seule
  personne a été découpée en plusieurs voix.
- **Repères en direct** : pendant une réunion, ta touche de dictée pose un repère sur
  l'instant courant. Ils sont listés en tête de la transcription.
- **Historique** local (dictées + réunions) groupé par jour, copiable et exportable en `.txt`
  ou en markdown, avec **recherche plein-texte** (mots-clés, accents ignorés) qui affiche le
  passage trouvé.
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

- **Dictée éclair** : maintiens la touche (par défaut **Option droite**), attends le petit son
  qui confirme que le micro écoute, parle, relâche. **Échap** annule la dictée en cours.
  Si le texte ne s'est pas collé, icône › **« Recoller la dernière dictée »**.
  Mode **mains libres** en option : un appui bref verrouille la capture, on parle sans rien
  tenir, un nouvel appui arrête.
- **Réunion** : icône › **« Démarrer une réunion »** … **« Arrêter la réunion »**.
  Pendant la réunion, ta touche de dictée **pose un repère** sur l'instant courant.
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
- **Séparation des locuteurs** : possible sur les fichiers importés (« Réunions › Séparer
  aussi les fichiers importés »). Compte environ **un quart de la durée de l'audio en plus**
  du temps de transcription. Le fichier reste traité par blocs, et les voix sont reconnues
  d'un bloc à l'autre : « Locuteur 2 » désigne la même personne du début à la fin.
- **Limites** : fichiers **protégés (DRM)** refusés ; une seule transcription à la fois
  (import, réunion ou dictée).

---

## ⚙️ Réglages (menu de l'icône)

| Réglage | Détail |
|---|---|
| **Qualité / vitesse** | Rapide (tiny) → Très précis (medium). Défaut : **Précis (small)**. Le **1er choix** d'une qualité télécharge le modèle une fois (jusqu'à ~1 min ; un message le signale), puis c'est hors-ligne. |
| **Langue** | **Français** (défaut), **Anglais**, ou **Automatique** (détecte la langue à chaque dictée — idéal pour alterner FR/EN). |
| **Touche de dictée** | Préréglages (Option droite par défaut, Cmd droite, Ctrl droite, F5) **ou « Choisir ma touche… »** : appuie sur la touche que tu veux, elle est captée telle quelle (fiable quel que soit le clavier). |
| **Réunions › Importer un fichier audio…** | Transcrit un fichier audio/vidéo existant comme une réunion (langue auto, découpage automatique, progression + annulation). |
| **Réunions › Horodatage** | Ajoute `[mm:ss]` en tête de chaque paragraphe (réunions **et** imports), pas devant chaque phrase. |
| **Réunions › Locuteurs attendus** | Un **plafond**, jamais un minimum : empêche de découper une voix en plusieurs, ne force jamais à fusionner. « 1 » = j'étais seul, la séparation ne tourne pas. |
| **Réunions › Séparer aussi les fichiers importés** | Étend la séparation aux imports (coûte ~25 % de la durée de l'audio en plus). |
| **Réunions › Exporter en markdown** | Le fichier exporté porte un titre et une date ; l'historique complet est groupé par jour. |
| **Touche de dictée › Mains libres** | Un appui bref verrouille la capture au lieu de l'ignorer. À éviter sur une touche modificatrice, qu'on effleure souvent. |
| **Texte dicté › Vocabulaire** | Ajoute les noms propres, marques et termes métier tels que tu veux les voir. Les variantes approchantes sont corrigées, même quand le moteur découpe le mot (*voie flash* → *VoixFlash*). Corrections exactes possibles, utilisables aussi comme raccourcis de saisie. |
| **Texte dicté › Retirer les hésitations** | Efface les « euh » et « hmm » du texte (activé). |
| **Texte dicté › Ajouter une espace après le texte collé** | Évite que deux dictées enchaînées se collent bord à bord (désactivé). |
| **Restaurer le presse-papiers** | Remet ton ancien presse-papiers après une dictée (activé), avec toutes ses données (image, texte enrichi, fichiers). |
| **Recoller la dernière dictée** | Filet de rattrapage quand un collage a échoué sans message. |

---

## 📁 Où sont mes fichiers ?

- Réglages, historique, journaux : `~/Library/Application Support/VoixFlash/`
- Transcriptions exportées (`.txt` datés) : `~/Documents/VoixFlash Transcriptions/`

---

## 🧹 Désinstallation

Double-clique sur **`uninstall.command`**. L'app s'arrête, le démarrage automatique est retiré
et ses fichiers sont supprimés. Tes transcriptions `.txt` déjà exportées sont conservées.

---

## 🛠️ Dépannage

- **Rien ne s'écrit en dictée éclair** → vérifie **Accessibilité** *et* **Surveillance des
  entrées**, puis **Redémarrer VoixFlash**.
- **La touche ne répond plus alors qu'elle marchait** → **Aide & autorisations › « La touche
  de dictée ne répond plus ? »**. Indice : si Option marche encore mais que F5 ne fait rien,
  c'est la **saisie sécurisée** de macOS (un champ mot de passe ouvert quelque part).
- **Pas de son capté** → vérifie **Microphone**. Si VoixFlash annonce que le micro n'a *rien*
  capté, c'est l'entrée elle-même qui est en cause : regarde **Réglages Système › Son**, et
  vérifie qu'aucune visio n'accapare le micro.
- **Pour demander de l'aide** → **Aide & autorisations › « Copier les informations système »**
  prépare un bloc à coller dans ton message (sans aucun texte dicté).
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
Aucun compte, aucune télémétrie. **Le texte que tu dictes n'est jamais journalisé** : le
journal de diagnostic audio ne contient que des compteurs techniques (le micro a-t-il livré
du son, et quand), sur une fenêtre de sept jours.

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
