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
- **Hors-ligne et privé** : moteur [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  sur **CPU uniquement**, rien n'est envoyé sur internet.
- **Léger et discret** : vit dans la barre des menus, quasi invisible au repos.
- **Accents français impeccables** : collage via le presse-papiers (jamais lettre par lettre).
- **Historique** local (dictées + réunions), copiable et exportable.
- **Réglages simples** : qualité/vitesse, langue (FR/EN), touche de dictée.

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
- **Indicateur** (barre des menus) : micro fin = chargement · micro plein = prêt · pastille
  d'enregistrement = enregistre · forme d'onde = transcrit · presse-papiers = écrit le texte.

Tout le reste (comportement du presse-papiers, limites, historique…) est détaillé dans le
**Mode d'emploi complet** intégré à l'app.

---

## ⚙️ Réglages (menu de l'icône)

| Réglage | Détail |
|---|---|
| **Qualité / vitesse** | Rapide (tiny) → Très précis (medium). Défaut : **Précis (small)**. |
| **Langue** | Français (défaut) ou Anglais. |
| **Touche de dictée** | Option droite (défaut), Cmd droite, Ctrl droite, F5. |
| **Réunions › Horodatage** | Ajoute `[mm:ss]` devant chaque passage. |
| **Restaurer le presse-papiers** | Remet ton ancien presse-papiers après une dictée (activé). |

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
