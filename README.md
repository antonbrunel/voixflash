# VoixFlash

Dictée vocale gratuite et 100 % hors-ligne pour Mac (Apple Silicon).
Une touche pour dicter partout, un bouton pour les réunions. Ta voix ne quitte jamais ton Mac.

> *Free, fully offline French/English dictation for Apple Silicon Macs. Menu bar app,
> faster-whisper on CPU. No account, no subscription, no cloud.*

## Ce que ça fait

- **Dictée éclair** : maintiens une touche, parle, relâche. Le texte s'écrit au curseur.
- **Réunions** : enregistrement long, transcription complète, export.
- **Import** : transcrit un fichier audio ou vidéo existant, y compris de 2 h et plus.
- **Locuteurs** : « Locuteur 1 », « Locuteur 2 », que tu peux renommer et fusionner.
- **Vocabulaire** : tes noms propres et ton jargon écrits correctement.
- **Historique** local, avec recherche plein texte.

Tout tourne en local sur le processeur. Mode d'emploi complet dans l'app :
icône VoixFlash › **Aide & autorisations**.

## Installation

1. Télécharge le projet (bouton vert **Code › Download ZIP**, ou une archive dans
   [Releases](../../releases)), puis décompresse-le.
2. Garde `install.command` et `voixflash.py` dans le **même dossier**.
3. Double-clique **`install.command`**. Quelques minutes la première fois.
4. L'icône micro apparaît dans la barre des menus.

Prérequis : Mac Apple Silicon, macOS récent, internet à l'installation seulement.
Rien n'est installé dans le système : tout vit dans `~/Library/Application Support/VoixFlash/`.

**App non signée** : au premier lancement, fais un **clic droit** sur `install.command` ›
**Ouvrir** › **Ouvrir**. Si macOS bloque encore, va dans **Réglages Système ›
Confidentialité et sécurité** et clique **« Ouvrir quand même »**.

## Autorisations (une seule fois)

Icône VoixFlash › **Aide & autorisations**, puis les trois boutons :

1. **Microphone** : pour entendre ta voix.
2. **Accessibilité** : pour coller le texte.
3. **Surveillance des entrées** : pour la touche de dictée.

Puis **Redémarrer VoixFlash**. Dans les listes de macOS, l'entrée à cocher apparaît sous
le nom **« Python »** : c'est normal tant que l'app n'est pas notarisée.

## Utilisation

**Dictée éclair** : maintiens la touche (par défaut **Option droite**), attends le petit son,
parle, relâche. **Échap** annule. Si rien ne s'est collé, icône › « Recoller la dernière dictée ».

**Réunion** : icône › « Démarrer une réunion », puis « Arrêter la réunion ». Pendant la
réunion, la touche de dictée **pose un repère** sur l'instant courant.

**Import** : icône › Réunions › « Importer un fichier audio… ». Langue détectée, progression
dans le menu, annulable sans perdre ce qui est déjà transcrit. Compte environ 15 min pour
1 h d'audio en qualité *small*.

**Icône** : micro fin = chargement · micro plein = prêt · pastille = enregistre ·
onde = transcrit · presse-papiers = écrit le texte.

## Réglages

| Réglage | Détail |
|---|---|
| **Qualité / vitesse** | *tiny* à *medium*, défaut *small*. Le 1er choix d'une qualité télécharge le modèle une fois. |
| **Langue** | Français, Anglais, ou Automatique. |
| **Touche de dictée** | Préréglages ou « Choisir ma touche… ». Mode **mains libres** en option (appui bref pour verrouiller). |
| **Texte dicté › Vocabulaire** | Tes noms propres respectés, même quand le moteur les découpe (*voie flash* devient *VoixFlash*). |
| **Réunions › Locuteurs attendus** | Un **plafond**, jamais un minimum. « 1 » désactive la séparation. |
| **Réunions › Séparer aussi les imports** | Ajoute environ 25 % de la durée de l'audio au traitement. |
| **Restaurer le presse-papiers** | Remet ton ancien contenu après une dictée, images et fichiers compris (activé). |

## Fichiers

- Réglages, historique, journaux : `~/Library/Application Support/VoixFlash/`
- Transcriptions exportées : `~/Documents/VoixFlash Transcriptions/`

**Désinstallation** : double-clique `uninstall.command`. Tes transcriptions déjà exportées
sont conservées.

## En cas de souci

- **Rien ne s'écrit** : vérifie **Accessibilité** *et* **Surveillance des entrées**, puis redémarre.
- **La touche ne répond plus alors qu'elle marchait** : Aide › « La touche de dictée ne
  répond plus ? ». Si Option marche mais pas F5, c'est la **saisie sécurisée** de macOS,
  déclenchée par un champ mot de passe ouvert quelque part.
- **Micro muet** : si VoixFlash annonce n'avoir rien capté du tout, c'est l'entrée elle-même.
  Regarde **Réglages Système › Son** et vérifie qu'aucune visio n'accapare le micro.
- **Demander de l'aide** : Aide › « Copier les informations système » prépare un bloc à coller.

## Vie privée

Tout est local. Aucun compte, aucune télémétrie. **Ce que tu dictes n'est jamais journalisé** :
le journal de diagnostic ne contient que des compteurs audio, sur une fenêtre de 7 jours.

## Technique

Python : `rumps` (barre des menus), `pynput` (clavier), `sounddevice` (audio),
`faster-whisper` en int8 sur CPU, `sherpa-onnx` pour les locuteurs (optionnel), SQLite.
L'installateur crée un environnement Python 3.12 isolé avec
[`uv`](https://github.com/astral-sh/uv).

```
install.command       Installateur (à double-cliquer)
uninstall.command     Désinstallateur
voixflash.py          L'application, commentée
build-release.command Fabrique l'archive .zip à partager
LISEZ-MOI.md          Guide rapide (inclus dans le .zip)
```

## Licence

Code : **MIT** (voir [LICENSE](LICENSE)). Bibliothèques tierces sous leurs propres licences :
faster-whisper et CTranslate2 (MIT), rumps (BSD), sounddevice et NumPy (BSD/MIT),
pyobjc (MIT), **pynput (LGPL-3.0)**.

Fourni tel quel, sans garantie. Non affilié à Apple.
