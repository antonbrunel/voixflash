#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VoixFlash — Dictée vocale gratuite et hors-ligne pour Mac (Apple Silicon).

Deux usages :
  1) Dictée éclair : on maintient une touche, on parle, on relâche, et le texte
     s'écrit tout seul là où se trouve le curseur (collage Cmd+V, accents parfaits).
  2) Réunion : on clique sur un bouton pour démarrer/arrêter ; le texte complet
     s'affiche dans l'application et peut être enregistré dans un fichier .txt daté.

Choix techniques (volontaires, voir le cahier des charges) :
  - Moteur faster-whisper, sur CPU uniquement (jamais le GPU/mps sur Apple Silicon).
  - Aucune connexion internet nécessaire après l'installation.
  - L'enregistrement et la transcription tournent dans des threads séparés :
    l'interface ne se fige jamais et, au repos, l'app ne consomme presque rien.
  - Le texte est inséré via le presse-papiers + un Cmd+V simulé (jamais lettre par
    lettre), ce qui garantit des accents français impeccables.
"""

import os
import re
import sys
import json
import time
import queue
import unicodedata
import socket
import sqlite3
import contextlib
import threading
import subprocess
import datetime

# Délais maximaux des appels réseau de Hugging Face. À poser AVANT d'importer
# faster_whisper : huggingface_hub lit ces variables au moment de son import. Sans
# elles, un CDN qui ne répond pas (portail captif, VPN, route IPv6 morte) laisse
# l'app coincée sur « chargement » indéfiniment, sans le moindre message.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "20")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "10")

import numpy as np
import sounddevice as sd
import rumps
from pynput import keyboard
from faster_whisper import WhisperModel

# PyAV est livré avec faster-whisper : il décode quasiment tout format audio/vidéo
# (mp3, m4a, wav, flac, ogg, aiff, et la piste audio des mp4/mov) SANS ffmpeg système.
# Sert à l'import d'un fichier audio (lecture de durée + décodage en flux vers 16 kHz mono).
try:
    import av
except Exception:  # si PyAV manquait, l'import de fichier sera simplement indisponible
    av = None

# Cacher l'icône du Dock : VoixFlash est une application "accessoire", visible
# uniquement dans la barre des menus en haut de l'écran.
try:
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
except Exception:  # au cas où AppKit ne serait pas disponible
    NSApplication = None
    NSApplicationActivationPolicyAccessory = None

# Sélecteur de fichier natif macOS (pour « Importer un fichier audio… »). Importé à
# part : si AppKit/NSOpenPanel manquait, l'import de fichier se rabat sur un message.
try:
    from AppKit import NSOpenPanel, NSModalResponseOK
except Exception:
    NSOpenPanel = None
    NSModalResponseOK = None

# Pour afficher une fenêtre modale au tour de boucle suivant, sans bloquer la
# boucle de rafraîchissement de l'interface.
try:
    from PyObjCTools import AppHelper
except Exception:
    AppHelper = None

# Boucle d'événements macOS. Sert à deux choses (cf. _install_timer_common_modes et
# _runloop_is_idle) : faire battre le minuteur d'interface même quand un menu est
# déroulé ou qu'une fenêtre est ouverte, et savoir dans quel mode on se trouve pour
# ne jamais reconstruire un menu pendant que l'utilisateur le parcourt.
try:
    from Foundation import NSRunLoop, NSDefaultRunLoopMode, NSRunLoopCommonModes
except Exception:
    NSRunLoop = None
    NSDefaultRunLoopMode = None
    NSRunLoopCommonModes = None


# --------------------------------------------------------------------------- #
#  Chemins & constantes
# --------------------------------------------------------------------------- #
APP_NAME = "VoixFlash"
APP_VERSION = "1.5.0"
LAUNCHD_LABEL = "com.voixflash.agent"   # étiquette du LaunchAgent (cf. install.command)
APP_HOME = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
CONFIG_PATH = os.path.join(APP_HOME, "config.json")
HISTORY_PATH = os.path.join(APP_HOME, "history.json")   # ancien format (migré vers SQLite)
HISTORY_DB = os.path.join(APP_HOME, "history.db")       # historique : base SQLite (scalable)
HISTORY_KEEP = 1000   # nombre max d'entrées conservées (purge auto des plus anciennes)

# Recherche plein-texte : disponible seulement si le SQLite embarqué gère le module
# FTS5. Positionné par history_init(). Sinon, history_search retombe sur un balayage
# simple (LIKE) — plus rudimentaire, mais l'historique est borné (HISTORY_KEEP).
_FTS_AVAILABLE = False
LOG_PATH = os.path.join(APP_HOME, "voixflash.log")
TRANSCRIPTS_DIR = os.path.expanduser(f"~/Documents/{APP_NAME} Transcriptions")

# Filet de sécurité des réunions : pendant TOUT l'enregistrement, l'audio est aussi
# écrit sur le disque, au fil de l'eau, dans ce dossier (PCM 16 bits mono brut + une
# petite fiche .json qui décrit le fichier). Si l'app est forcée à quitter, plante,
# ou que le Mac s'éteint, l'enregistrement n'est PAS perdu : il est retrouvé et
# proposé à la transcription au démarrage suivant (cf. _check_interrupted_meetings).
MEETING_RAW_DIR = os.path.join(APP_HOME, "reunions_interrompues")
MEETING_RAW_PREFIX = "reunion_"

# Au-delà de ce nombre de caractères, une transcription n'est plus affichée dans une
# fenêtre : le champ de saisie de rumps est un NSTextField simple (sans défilement),
# dont la mise en page rame très fort sur un long texte et fige le thread principal.
# On passe alors par un fichier .txt ouvert dans TextEdit.
LONG_TEXT_CHARS = 4000

# --- Séparation des locuteurs (diarisation) — module OPTIONNEL, installé à la demande -
# Moteur : sherpa-onnx (onnxruntime, hors-ligne). Les modèles ONNX sont hébergés sur les
# Releases GitHub de sherpa-onnx → aucun compte ni téléchargement HuggingFace, aucune clé.
# Volontairement PAS une dépendance de base : VoixFlash reste léger par défaut ; cette
# couche ne s'ajoute QUE si l'utilisateur l'active depuis le menu « Réunions » (elle
# télécharge alors sherpa-onnx + ~44 Mo de modèles, une seule fois, puis tout est local).
DIAR_DIR = os.path.join(APP_HOME, "models", "diarization")
DIAR_SEG_PATH = os.path.join(DIAR_DIR, "segmentation.onnx")   # pyannote 3.0 (ONNX) : ~6 Mo
DIAR_EMB_PATH = os.path.join(DIAR_DIR, "embedding.onnx")      # empreintes locuteurs : ~38 Mo
DIAR_SEG_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")
DIAR_EMB_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                "speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")
# Choix « nombre de locuteurs attendus » proposé dans le menu (libellé, valeur ; 0 = auto).
DIAR_SPEAKER_CHOICES = [("Automatique", 0), ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6)]

# Outils macOS appelés en chemin absolu (fiabilité quand l'app est lancée par launchd).
PBCOPY = "/usr/bin/pbcopy"
PBPASTE = "/usr/bin/pbpaste"
OPEN = "/usr/bin/open"

# pbcopy/pbpaste interprètent leur entrée selon la locale. Lancé par launchd, le
# processus n'a souvent pas de variable LANG → les accents seraient abîmés. On force
# donc un encodage UTF-8 pour toutes les opérations de presse-papiers.
CLIP_ENV = {**os.environ, "LANG": "en_US.UTF-8", "LC_CTYPE": "en_US.UTF-8"}

# Garde-fous de durée : évite un micro oublié et une consommation mémoire qui gonfle.
MAX_MEETING_SECONDS = 3 * 60 * 60   # arrêt auto d'une réunion après 3 h
MAX_FLASH_SECONDS = 120             # dictée éclair maintenue anormalement longtemps

# --- Import d'un fichier audio (menu Réunions › « Importer un fichier audio… ») -------
# On ne décode JAMAIS le fichier entier en mémoire : on le lit en flux et on le transcrit
# par BLOCS. Un fichier de 2 h ferait sinon ~460 Mo de float32 16 kHz en RAM, en plus du
# modèle. Le découpage borne la mémoire (~un bloc à la fois), permet d'afficher une
# progression, de sauvegarder au fil de l'eau, et d'annuler proprement.
IMPORT_CHUNK_SECONDS = 8 * 60       # durée cible d'un bloc de transcription (~30 Mo en RAM)
IMPORT_CUT_SEARCH_SEC = 20         # fenêtre (s) où chercher un silence pour couper le bloc
IMPORT_WARN_SECONDS = 30 * 60      # au-delà : on prévient + estimation de temps avant de lancer
IMPORT_MAX_SECONDS = MAX_MEETING_SECONDS   # 3 h : confirmation forte au-delà (RAM/temps)
IMPORT_CHUNK_PAUSE = 0.25          # courte pause entre blocs : laisse respirer le CPU/thermique
# Facteur « temps de calcul ≈ durée audio × facteur » selon le modèle, sur CPU int8 Apple
# Silicon. Sert UNIQUEMENT à donner une estimation indicative avant un long import.
IMPORT_RT_FACTOR = {"tiny": 0.06, "base": 0.1, "small": 0.25,
                    "medium": 0.6, "large-v3": 1.2, "large-v2": 1.2}
# Nombre de threads CPU laissés au moteur : on garde 2 cœurs libres pour que la machine
# reste utilisable pendant une transcription longue (réunions ET imports en profitent).
CPU_THREADS = max(1, (os.cpu_count() or 4) - 2)

os.makedirs(APP_HOME, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
os.makedirs(MEETING_RAW_DIR, exist_ok=True)

# Réglages par défaut (modifiables depuis le menu, sauvegardés dans config.json).
DEFAULT_CONFIG = {
    "hotkey": "alt_r",            # touche de dictée éclair = Option (alt) droite
    "hotkey_label": "Option droite",  # libellé lisible de la touche (affichage)
    "model": "small",            # qualité/vitesse de transcription (défaut équilibré)
    "language": "fr",            # langue : "fr", "en", ou "auto" (détection automatique)
    "meeting_timestamps": False,  # ajouter [mm:ss] devant chaque passage des réunions
    "restore_clipboard": True,    # remettre l'ancien presse-papiers après le collage
    "beam_size": 5,              # qualité du décodage (5 = bon compromis)
    "mic_primed": False,         # le micro a-t-il déjà été « amorcé » (demande d'autorisation déclenchée) ?
    "diarization_enabled": False,  # séparer les locuteurs en réunion (« Locuteur 1 : … »)
    "diarization_speakers": 0,   # nb de locuteurs attendus (0 = détection automatique)
    "remove_hesitations": True,  # retirer les « euh », « hmm » du texte transcrit
    "sounds_enabled": True,      # petits sons au début et à la fin d'une dictée
}

# Traîne conservée après le relâchement de la touche. Le dernier mot est encore en
# vol dans les tampons de CoreAudio au moment du relâchement : couper net le tronque.
RELEASE_TAIL_S = 0.2
# En deçà, l'appui n'est pas une dictée (touche effleurée). Cf. _on_release : la règle
# ne vaut QUE pour une touche modificatrice.
SHORT_TAP_S = 0.3

# Amorce de style passée à Whisper : ce n'est PAS du vocabulaire, mais une phrase
# correctement ponctuée et accentuée dans la langue visée. Le modèle poursuit dans
# le registre de son amorce, donc il ponctue et il accentue mieux. Volontairement
# très courte : Whisper tronque l'amorce au-delà de 224 jetons, et une amorce
# chargée de vocabulaire dégraderait la transcription au lieu de l'aider.
STYLE_PROMPTS = {
    "fr": "Bonjour, comment allez-vous ? Ravi de vous rencontrer.",
    "en": "Hello, how are you? Nice to meet you.",
}

# Icône d'état dans la barre des menus. On utilise des symboles SF (les mêmes
# glyphes vectoriels que macOS), rendus en « template » : ils s'affichent en blanc
# (ou noir) comme les autres icônes natives de la barre, sans dénoter. L'état est
# indiqué par la FORME du glyphe (le blanc interdit les couleurs rouge/orange).
STATE_SYMBOLS = {
    "loading": "mic",                 # micro fin (contour) : le moteur se charge
    "idle": "mic.fill",               # micro plein : prêt
    "recording": "record.circle",     # pastille d'enregistrement : on capte
    "transcribing": "waveform",       # forme d'onde : on transcrit
    "pasting": "doc.on.clipboard",    # presse-papiers : on écrit le texte
}

# Libellés du menu réunion (sans emoji : ils dénotaient dans un menu macOS natif).
MEETING_START_TITLE = "Démarrer une réunion"
MEETING_STOP_TITLE = "Arrêter la réunion"
# Pendant la transcription d'une réunion, l'item affiche la progression et sert de
# bouton d'annulation : une transcription d'1 h prend plusieurs minutes, et sans
# aucun retour à l'écran on ne distingue pas « ça travaille » de « c'est planté ».
MEETING_TRANSCRIBE_TITLE = "Transcription en cours…"

# Libellés de l'item « Importer un fichier audio » (qui bascule en « Annuler » pendant
# qu'un import est en cours de transcription).
IMPORT_IDLE_TITLE = "Importer un fichier audio…"
IMPORT_CANCEL_TITLE = "Annuler la transcription en cours"

# Repli (anciens macOS sans symboles SF) : on garde de simples emojis comme titre.
STATE_TITLES = {
    "loading": "⏳",       # le moteur de transcription se charge
    "idle": "🟢",          # prêt
    "recording": "🔴",     # en train d'enregistrer
    "transcribing": "🟠",  # en train de transcrire
    "pasting": "✍️",       # en train d'écrire le texte
}

# Choix de qualité proposés dans le menu (libellé, nom du modèle faster-whisper).
MODEL_CHOICES = [
    ("Rapide (tiny)", "tiny"),
    ("Standard (base)", "base"),
    ("Précis (small)", "small"),
    ("Très précis (medium)", "medium"),
]

# Choix de touche de dictée proposés dans le menu (libellé, valeur pynput).
HOTKEY_CHOICES = [
    ("Option droite", "alt_r"),
    ("Cmd droite", "cmd_r"),
    ("Ctrl droite", "ctrl_r"),
    ("Touche F5", "f5"),
]


# --------------------------------------------------------------------------- #
#  Petites fonctions utilitaires
# --------------------------------------------------------------------------- #
def log(msg):
    """Écrit un message horodaté dans le journal (utile en cas de souci)."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}  {msg}\n")
    except Exception:
        pass


def load_json(path, default):
    """Lit un fichier JSON ; renvoie `default` s'il est absent ou illisible."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    """Écrit un JSON de façon sûre (écriture dans un fichier temporaire puis renommage)."""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log(f"save_json {path}: {e}")


def fmt_ts(seconds):
    """Met en forme un horodatage en mm:ss."""
    seconds = int(seconds or 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def fmt_duration(seconds):
    """Durée lisible pour un humain : « 45 s », « 12 min » ou « 1 h 23 »."""
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    h, m = divmod(seconds // 60, 60)
    return f"{h} h {m:02d}"


def parse_hotkey(s):
    """Transforme une valeur de config en touche pynput. Formats acceptés :
      - 'vk:50'   → touche par CODE PHYSIQUE (le plus fiable, indépendant du clavier)
      - 'char:²'  → touche par caractère
      - 'alt_r', 'f5', 'cmd_r'… → touche nommée (préréglages)
      - 'a'       → caractère unique (compatibilité ancienne config)"""
    s = (s or "").strip()
    if s.startswith("vk:"):
        try:
            return keyboard.KeyCode.from_vk(int(s[3:]))
        except Exception:
            return keyboard.Key.alt_r
    if s.startswith("char:"):
        c = s[5:]
        return keyboard.KeyCode.from_char(c) if c else keyboard.Key.alt_r
    low = s.lower()
    if hasattr(keyboard.Key, low):              # touche spéciale (alt_r, f5, cmd_r...)
        return getattr(keyboard.Key, low)
    if len(s) == 1:                             # touche caractère normale
        return keyboard.KeyCode.from_char(s)
    return keyboard.Key.alt_r                   # repli sûr : Option droite


def serialize_hotkey(key):
    """Transforme une touche pynput captée en chaîne stockable dans la config.
    On privilégie le CODE PHYSIQUE (vk) : il identifie la touche par sa position,
    sans dépendre de la disposition clavier ni du fait que la touche produise ou
    non un caractère — c'est ce qui évite les soucis du type Option droite vue
    comme « alt_r » sur un Mac et « alt_gr » sur un autre."""
    try:
        if isinstance(key, keyboard.Key):
            return key.name                      # touche nommée (alt_r, f5, alt_gr…)
        vk = getattr(key, "vk", None)
        if vk is not None:
            return f"vk:{vk}"
        ch = getattr(key, "char", None)
        if ch:
            return f"char:{ch}"
    except Exception:
        pass
    return None


def key_matches(key, target):
    """Compare une touche reçue à la touche de dictée configurée. On compare en
    priorité le CODE PHYSIQUE (vk) : robuste quelle que soit la disposition."""
    try:
        if isinstance(target, keyboard.Key):
            return key == target
        # target est un KeyCode (touche capturée). On compare d'abord par vk.
        tvk = getattr(target, "vk", None)
        kvk = getattr(key, "vk", None)
        if tvk is not None and kvk is not None:
            return kvk == tvk
        tchar = getattr(target, "char", None)
        kchar = getattr(key, "char", None)
        if tchar is not None and kchar is not None:
            return kchar == tchar
        return key == target
    except Exception:
        return False


def hotkey_display(key):
    """Libellé lisible (français) pour une touche pynput captée."""
    named = {
        "alt_r": "Option droite", "alt_l": "Option gauche", "alt": "Option",
        "alt_gr": "Option droite (AltGr)",
        "cmd_r": "Cmd droite", "cmd_l": "Cmd gauche", "cmd": "Cmd",
        "ctrl_r": "Ctrl droite", "ctrl_l": "Ctrl gauche", "ctrl": "Ctrl",
        "shift_r": "Maj droite", "shift_l": "Maj gauche", "shift": "Maj",
        "space": "Espace", "tab": "Tabulation", "caps_lock": "Verr. Maj",
    }
    try:
        if isinstance(key, keyboard.Key):
            return named.get(key.name, key.name.replace("_", " ").upper())
        ch = getattr(key, "char", None)
        if ch and ch.strip():
            return f"« {ch} »"
        vk = getattr(key, "vk", None)
        if vk is not None:
            return f"touche (code {vk})"
    except Exception:
        pass
    return "touche"


# Sur du silence ou du bruit, Whisper « hallucine » des phrases parasites récurrentes
# (crédits de sous-titres). En dictée éclair (VAD désactivé pour ne jamais perdre un
# mot), elles seraient collées dans le document. On écarte UNIQUEMENT des marqueurs qui
# ne sont jamais une vraie dictée — volontairement conservateur : mieux vaut laisser
# passer une rare hallucination que supprimer par erreur de la vraie parole.
HALLUCINATION_MARKERS = (
    "amara.org",
    "sous-titres réalisés par",
    "sous-titrage société radio-canada",
    "soustitreur.com",
)


def is_probably_hallucination(text):
    """True si le texte se résume à une phrase parasite connue de Whisper (silence)."""
    t = " ".join((text or "").lower().split())
    return bool(t) and any(marker in t for marker in HALLUCINATION_MARKERS)


# ------------------------------------------------- post-traitement du texte --
# Tout se fait APRÈS la transcription, sur la sortie réelle du modèle. Le
# vocabulaire n'est volontairement PAS passé au décodeur (hotwords /
# initial_prompt) : les projets concurrents qui l'ont fait ont dû le désactiver
# en urgence, de courtes listes de mots dominant la sortie et DÉGRADANT le taux
# d'erreur. Corriger après coup donne l'essentiel du bénéfice sans ce risque.

VOCAB_PATH = os.path.join(APP_HOME, "vocabulaire.json")

# Hésitations pures : ce ne sont des mots ni en français ni en anglais.
FILLERS_UNIVERSAL = ("euh", "euhm", "euhh", "heu", "heuh", "hmm", "hmmm",
                     "hum", "humm", "mmm", "mmh", "ehm", "ehmm")
# Hésitations anglaises : « um » est un mot dans d'autres langues (portugais),
# on ne les retire donc que si la langue anglaise est établie.
FILLERS_EN = ("um", "umm", "uh", "uhm", "erm")

# Un mot = lettres/chiffres, apostrophes internes comprises (« aujourd'hui »).
WORD_RE = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)


def strip_accents(s):
    """Retire les signes diacritiques (é → e)."""
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def fold_key(s):
    """Clé de rapprochement : minuscules, sans accents, sans ponctuation.

    C'est elle qui fait que « Grôb » rejoint « Grob » et « voie flash »
    rejoint « VoixFlash » (une seule substitution d'écart)."""
    return "".join(ch for ch in strip_accents(s).lower() if ch.isalnum())


def edit_distance(a, b, cap):
    """Distance de Levenshtein, abandonnée dès qu'elle dépasse `cap`.

    L'abandon anticipé est ce qui rend le rapprochement utilisable sur une
    réunion entière : la grande majorité des paires est écartée en une ligne."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (0 if ca == cb else 1)))
            if cur[j] < best:
                best = cur[j]
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


# ------------------------------------------------------------ retours sonores --
# Sans retour sonore, on ne sait pas si la touche a bien été prise, on parle trop
# tôt, et le début de la phrase est perdu. C'est la panne la plus courante d'une
# dictée en maintien de touche, et elle ne se voit pas : la transcription est
# simplement incomplète.

MODIFIER_KEYS = frozenset(name for name in (
    "alt", "alt_l", "alt_r", "alt_gr", "cmd", "cmd_l", "cmd_r",
    "ctrl", "ctrl_l", "ctrl_r", "shift", "shift_l", "shift_r")
    if hasattr(keyboard.Key, name))


def hotkey_is_modifier(key):
    """True si la touche de dictée est un simple modificateur (Option, Cmd…).

    Ces touches n'écrivent rien, donc on peut les maintenir en sécurité dans un
    document. En contrepartie, elles se combinent avec d'autres : c'est le seul
    cas où un appui très court, ou l'arrivée d'une autre touche, doit annuler."""
    try:
        return isinstance(key, keyboard.Key) and key.name in MODIFIER_KEYS
    except Exception:
        return False


def input_is_bluetooth():
    """True si l'entrée audio courante ressemble à un périphérique Bluetooth.

    Ouvrir une entrée ET une sortie en même temps sur un casque Bluetooth force
    macOS à basculer en profil « mains libres » : le son devient téléphonique et
    les écouteurs peuvent être arrachés à l'appareil qui les utilisait. On évite
    donc de jouer un son quand le micro Bluetooth est ouvert."""
    try:
        name = str(sd.query_devices(kind="input").get("name", "")).lower()
    except Exception:
        return False
    return any(m in name for m in ("airpods", "bluetooth", "hands-free", "headset", "beats"))


def secure_input_enabled():
    """True si un processus a activé la « saisie sécurisée » (champ mot de passe…).

    Dans cet état, macOS cesse de livrer les APPUIS de touches aux applications
    tierces mais continue de livrer les changements de modificateurs. Conséquence
    déroutante : une touche de dictée modificatrice (Option) marche encore, tandis
    qu'un raccourci contenant une vraie touche (F5) devient totalement muet, sans
    le moindre message. C'est la première chose à regarder quand la dictée « ne
    répond plus ». Renvoie None si l'information n'est pas récupérable."""
    try:
        import ctypes
        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/Carbon.framework/Carbon")
        lib.IsSecureEventInputEnabled.restype = ctypes.c_bool
        lib.IsSecureEventInputEnabled.argtypes = []
        return bool(lib.IsSecureEventInputEnabled())
    except Exception as e:
        log(f"saisie sécurisée (lecture) : {e}")
        return None


try:
    import objc
    from AppKit import NSObject as _NSObject

    class WakeObserver(_NSObject):
        """Reçoit la notification de réveil du Mac et la transmet à l'application."""

        def initWithCallback_(self, callback):
            self = objc.super(WakeObserver, self).init()
            if self is None:
                return None
            self._callback = callback
            return self

        def onWake_(self, _notification):
            try:
                self._callback()
            except Exception as e:
                log(f"réveil : {e}")
except Exception as _e:                      # pyobjc absent ou trop ancien
    log(f"observateur de réveil indisponible : {_e}")
    WakeObserver = None


class Sounds:
    """Retours sonores, lecteurs préparés une fois pour toutes.

    Instancier le lecteur au moment du déclenchement coûterait plus cher que le
    son lui-même et retarderait le retour, qui n'a d'intérêt que s'il est immédiat.
    Passer par `afplay` en sous-processus serait pire encore (environ 100 ms rien
    que pour lancer le programme)."""

    NAMES = {"start": "Tink", "stop": "Pop", "error": "Basso"}

    def __init__(self, volume=0.3):
        self._players = {}
        self._ui_sounds_on = True
        try:
            from AppKit import NSSound, NSUserDefaults
            for key, name in self.NAMES.items():
                player = NSSound.soundNamed_(name)
                if player is not None:
                    player.setVolume_(volume)
                    self._players[key] = player
            # Respecte « Émettre les effets sonores de l'interface » des réglages macOS.
            domain = NSUserDefaults.standardUserDefaults().persistentDomainForName_(
                "Apple Global Domain") or {}
            value = domain.get("com.apple.sound.uiaudio.enabled")
            if value is not None:
                self._ui_sounds_on = bool(value)
        except Exception as e:
            log(f"retours sonores indisponibles : {e}")

    def play(self, which):
        """Joue un retour. Ne lève jamais : un son raté ne doit rien casser."""
        if not self._ui_sounds_on:
            return
        player = self._players.get(which)
        if player is None:
            return
        try:
            if player.isPlaying():
                player.stop()
            player.play()
        except Exception as e:
            log(f"lecture du son « {which} » : {e}")


def fail_open(step):
    """Une étape de nettoyage ne doit JAMAIS faire perdre une dictée réussie.

    En cas d'erreur (règle mal formée, entrée exotique), on rend le texte reçu
    tel quel plutôt que de propager l'exception."""
    def wrapper(text, *args, **kwargs):
        try:
            out = step(text, *args, **kwargs)
            return out if isinstance(out, str) else text
        except Exception as e:
            log(f"post-traitement « {step.__name__} » ignoré : {e}")
            return text
    wrapper.__name__ = step.__name__
    return wrapper


@fail_open
def remove_fillers(text, language="fr"):
    """Retire les hésitations, avec la virgule orpheline qu'elles laissent."""
    words = list(FILLERS_UNIVERSAL)
    if language == "en":
        words += list(FILLERS_EN)
    pattern = r"\b(?:%s)\b[^\S\n]*,?" % "|".join(re.escape(w) for w in words)
    return re.sub(pattern, "", text, flags=re.IGNORECASE)


@fail_open
def collapse_stutters(text):
    """Trois répétitions consécutives ou plus d'un même mot → une seule.

    Deux répétitions sont conservées volontairement : « non non c'est bon »
    est une vraie tournure, alors que « je je je » est un bégaiement de Whisper."""
    return re.sub(r"\b(\w+)((?:[^\S\n]+\1\b){2,})", r"\1", text, flags=re.IGNORECASE)


@fail_open
def apply_corrections(text, corrections):
    """Remplacements exacts déclencheur → remplacement, les plus longs d'abord.

    Le remplacement passe par une fonction et jamais par une chaîne de motif :
    sinon un « $ » ou un « \\ » dans le texte de remplacement serait interprété."""
    for trigger in sorted(corrections, key=len, reverse=True):
        repl = corrections[trigger]
        text = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(trigger),
                      lambda _m, r=repl: r, text, flags=re.IGNORECASE)
    return text


@fail_open
def apply_vocabulary(text, words, threshold=0.18):
    """Rapproche les groupes de 1 à 3 mots du vocabulaire de l'utilisateur.

    Les groupes servent à rattraper ce que Whisper découpe (« voie flash » →
    « VoixFlash »). Un candidat n'est retenu que si sa distance d'édition
    rapportée à sa longueur passe sous le seuil : les mots courts sont donc
    naturellement protégés, une seule faute y pesant trop lourd."""
    targets = [(w, fold_key(w)) for w in (words or [])]
    targets = [(w, k) for (w, k) in targets if k and len(k) <= 50]
    if not targets:
        return text
    tokens = [(m.start(), m.end()) for m in WORD_RE.finditer(text)]
    if not tokens:
        return text
    out, last, i = [], 0, 0
    while i < len(tokens):
        hit = None
        for n in (3, 2, 1):
            if i + n > len(tokens):
                continue
            start, end = tokens[i][0], tokens[i + n - 1][1]
            span = text[start:end]
            # Un groupe ne franchit jamais une ponctuation : « ... flash. Voie ... »
            # ne doit pas être recollé en un seul candidat.
            if n > 1 and re.search(r"[^\w \t'’-]", span):
                continue
            key = fold_key(span)
            if not key or len(key) > 50:
                continue
            best = None
            for (w, wk) in targets:
                if wk == key:
                    # Mêmes lettres à la casse et aux accents près : c'est l'usage
                    # « ancre » du vocabulaire (imposer Grob, Kubernetes, VoixFlash).
                    # Ce cas doit passer AVANT la protection des mots courts.
                    best = (0.0, w)
                    break
                longest = max(len(wk), len(key))
                if abs(len(wk) - len(key)) > max(2, longest // 4):
                    continue
                cap = int(threshold * longest)
                if cap < 1:
                    continue          # mot trop court pour tolérer la moindre faute
                d = edit_distance(key, wk, cap)
                if d <= cap:
                    score = d / longest
                    if best is None or score < best[0]:
                        best = (score, w)
            if best is not None:
                hit = (start, end, best[1], n)
                break
        if hit:
            start, end, word, n = hit
            out.append(text[last:start])
            out.append(word)
            last = end
            i += n
        else:
            i += 1
    out.append(text[last:])
    return "".join(out)


@fail_open
def tidy_spacing(text):
    """Espaces multiples et espaces parasites laissés par les étapes précédentes.

    On ne touche PAS aux espaces avant « ; : ! ? » : la typographie française
    les exige, et Whisper les produit correctement."""
    text = re.sub(r"[^\S\n]{2,}", " ", text)
    text = re.sub(r"[^\S\n]+([,.])", r"\1", text)
    text = re.sub(r"[^\S\n]*\n[^\S\n]*", "\n", text)
    return text.strip()


def load_vocabulary():
    """Lit le vocabulaire de l'utilisateur (mots à faire respecter, corrections)."""
    data = load_json(VOCAB_PATH, None)
    if not isinstance(data, dict):
        return {"mots": [], "corrections": {}}
    mots = [w.strip() for w in (data.get("mots") or [])
            if isinstance(w, str) and w.strip()]
    corrections = {k.strip(): v for k, v in (data.get("corrections") or {}).items()
                   if isinstance(k, str) and isinstance(v, str) and k.strip()}
    return {"mots": mots, "corrections": corrections}


def postprocess_text(text, language="fr", vocab=None, remove_hesitations=True):
    """Chaîne de nettoyage locale, déterministe et sans inférence."""
    if not text:
        return text
    text = unicodedata.normalize("NFC", text)
    started_upper = text[:1].isupper()
    if remove_hesitations:
        text = remove_fillers(text, language)
    vocab = vocab or {}
    text = apply_vocabulary(text, vocab.get("mots"))
    text = apply_corrections(text, vocab.get("corrections") or {})
    text = collapse_stutters(text)
    text = tidy_spacing(text)
    # « Euh, demain matin » ne doit pas devenir « demain matin » en minuscule.
    if started_upper and text[:1].islower():
        text = text[:1].upper() + text[1:]
    return text


def model_is_cached(name):
    """True si le modèle faster-whisper « name » est DÉJÀ téléchargé (cache Hugging
    Face) → son chargement sera rapide, sans réseau. False = 1er usage = téléchargement
    (potentiellement long). Sert à prévenir l'utilisateur uniquement quand c'est utile."""
    try:
        base = (os.environ.get("HF_HUB_CACHE")
                or os.environ.get("HUGGINGFACE_HUB_CACHE"))
        if not base:
            hf_home = os.environ.get("HF_HOME")
            base = os.path.join(hf_home, "hub") if hf_home else \
                os.path.expanduser("~/.cache/huggingface/hub")
        snap = os.path.join(base, f"models--Systran--faster-whisper-{name}", "snapshots")
        if not os.path.isdir(snap):
            return False
        # Le modèle n'est « complet » que si un instantané contient model.bin.
        for d in os.listdir(snap):
            if os.path.isfile(os.path.join(snap, d, "model.bin")):
                return True
        return False
    except Exception:
        return False


def audio_stream_info(path):
    """Renvoie (durée_en_secondes | None, a_une_piste_audio: bool) pour un fichier média.

    Lecture des MÉTADONNÉES uniquement (aucun décodage) : c'est instantané, ce qui permet
    de prévenir l'utilisateur AVANT de lancer un long décodage. Renvoie (None, False) si le
    fichier est illisible, protégé (DRM), ou n'est pas un média — l'appelant affiche alors
    un message clair plutôt que de planter."""
    if av is None:
        return (None, False)
    try:
        with av.open(path) as container:
            audio_streams = [s for s in container.streams if s.type == "audio"]
            if not audio_streams:
                return (None, False)               # aucune piste audio dans le fichier
            dur = None
            if container.duration:                 # micro-secondes (av.time_base = 1e6)
                dur = float(container.duration) / av.time_base
            else:                                  # repli : durée portée par le flux audio
                st = audio_streams[0]
                if st.duration and st.time_base:
                    dur = float(st.duration * st.time_base)
            return (dur, True)
    except Exception as e:
        log(f"audio_stream_info({os.path.basename(path)}) : {e}")
        return (None, False)


def iter_audio_chunks(path, cancel_check=None):
    """Décode un fichier média EN FLUX et le restitue par BLOCS float32 16 kHz mono.

    Générateur de tuples (audio_float32, start_sec), où start_sec est l'horodatage (en
    secondes) du début du bloc dans le fichier d'origine — indispensable pour réaligner
    l'horodatage des passages sur toute la durée.

    Choix de conception (tous au service d'un import long et propre) :
    • Mémoire bornée : on n'accumule qu'un bloc (~IMPORT_CHUNK_SECONDS) à la fois, jamais le
      fichier entier. Un fichier de 5 h se transcrit avec la même empreinte mémoire qu'un de 5 min.
    • Coupe dans le SILENCE : quand le tampon dépasse la taille cible, on cherche la fenêtre
      de 0,5 s la moins énergique (RMS mini) autour de la frontière et on coupe LÀ — jamais
      au milieu d'un mot. Aucun chevauchement ni dédoublonnage n'est donc nécessaire.
    • Rééchantillonnage systématique vers 16 kHz mono (quel que soit le format/canaux source).
    • Annulable : si cancel_check() devient vrai, on s'arrête après le bloc en cours."""
    if av is None:
        raise RuntimeError("PyAV indisponible : impossible de décoder le fichier.")
    SR = 16000
    target = int(IMPORT_CHUNK_SECONDS * SR)
    search = int(IMPORT_CUT_SEARCH_SEC * SR)
    win = int(0.5 * SR)                 # fenêtre d'analyse d'énergie : 0,5 s
    resampler = av.AudioResampler(format="flt", layout="mono", rate=SR)
    parts = []                          # morceaux float32 en attente d'émission
    pending = 0                         # total d'échantillons dans `parts`
    emitted = 0                         # échantillons déjà émis (→ start_sec du bloc suivant)

    def _push(arr):
        nonlocal pending
        if arr.size:
            parts.append(arr)
            pending += arr.size

    def _best_cut(b):
        # Indice de coupe au creux d'énergie dans [target-search, target+search], borné.
        lo = max(win, target - search)
        hi = min(len(b) - win, target + search)
        if hi <= lo:
            return min(target, len(b))
        best_i, best_e = lo, None
        step = max(1, win // 2)
        for i in range(lo, hi, step):
            e = float(np.mean(b[i:i + win] ** 2))
            if best_e is None or e < best_e:
                best_e, best_i = e, i
        return best_i

    cancelled = False
    with av.open(path) as container:
        astream = next((s for s in container.streams if s.type == "audio"), None)
        if astream is None:
            raise RuntimeError("Le fichier ne contient pas de piste audio.")
        for frame in container.decode(astream):
            if cancel_check and cancel_check():
                cancelled = True
                break
            for r in resampler.resample(frame):
                _push(r.to_ndarray().reshape(-1).astype(np.float32))
            while pending >= target + search:
                b = np.concatenate(parts)
                cut = _best_cut(b)
                yield b[:cut], emitted / SR
                emitted += cut
                rem = b[cut:]
                parts = [rem]
                pending = rem.size
        # Vider le rééchantillonneur (frames en attente) puis émettre le reliquat final —
        # sauf si l'utilisateur a annulé (on garde alors uniquement ce qui a déjà été émis).
        if not cancelled:
            try:
                for r in resampler.resample(None):
                    _push(r.to_ndarray().reshape(-1).astype(np.float32))
            except Exception:
                pass
            if pending > 0:
                yield np.concatenate(parts), emitted / SR


def accessibility_trusted():
    """True si l'app a l'autorisation « Accessibilité » (nécessaire pour coller le texte).
    Renvoie True si l'information est indéterminable, afin de ne jamais bloquer à tort."""
    for mod in ("ApplicationServices", "HIServices", "Quartz"):
        try:
            m = __import__(mod, fromlist=["AXIsProcessTrusted"])
            if hasattr(m, "AXIsProcessTrusted"):
                return bool(m.AXIsProcessTrusted())
        except Exception:
            continue
    return True


def app_to_front():
    """Passe VoixFlash au premier plan.

    ⚠ À appeler AVANT toute fenêtre modale (alerte, fenêtre de saisie, sélecteur de
    fichier). VoixFlash est une application « accessoire » : elle n'est jamais l'app
    active. Une NSAlert ouverte dans cet état apparaît DERRIÈRE la fenêtre dans
    laquelle on travaille — invisible — alors que son runModal() bloque le thread
    principal jusqu'au clic. L'app semble alors totalement gelée (icône figée, menu
    qui ne s'ouvre plus) et la seule issue est de forcer la fermeture. C'était la
    cause n°1 des blocages signalés."""
    if NSApplication is None:
        return
    try:
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception as e:
        log(f"activation au premier plan : {e}")


def internet_reachable(host="huggingface.co", port=443, timeout=5.0):
    """True si l'hôte répond en moins de `timeout` secondes.

    Sert de garde-fou AVANT le seul appel réseau bloquant de l'app (téléchargement
    d'un modèle absent du cache) : mieux vaut un message clair en 5 s qu'une app
    coincée sur « chargement » pour toujours."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        log(f"réseau injoignable ({host}:{port}) : {e}")
        return False


# ---------------------------------------------- filet de sécurité des réunions --
def meeting_backup_paths(stamp):
    """Couple (fichier audio brut, fiche descriptive) d'une sauvegarde de réunion."""
    base = os.path.join(MEETING_RAW_DIR, f"{MEETING_RAW_PREFIX}{stamp}")
    return base + ".raw", base + ".json"


def meeting_backup_duration(raw_path, sr):
    """Durée (s) d'une sauvegarde brute, déduite de sa taille (PCM 16 bits mono)."""
    try:
        return os.path.getsize(raw_path) / (2.0 * max(1, int(sr)))
    except OSError:
        return 0.0


def find_interrupted_meetings():
    """Liste les sauvegardes de réunions restées sur le disque (donc jamais transcrites),
    de la plus ancienne à la plus récente. Chaque élément : (raw, json, sr, durée)."""
    found = []
    try:
        names = sorted(os.listdir(MEETING_RAW_DIR))
    except OSError:
        return found
    for name in names:
        if not (name.startswith(MEETING_RAW_PREFIX) and name.endswith(".raw")):
            continue
        raw = os.path.join(MEETING_RAW_DIR, name)
        meta_path = raw[:-4] + ".json"
        meta = load_json(meta_path, {})
        sr = int(meta.get("sr") or 16000)
        dur = meeting_backup_duration(raw, sr)
        if dur < 1.0:          # moins d'une seconde : rien d'exploitable, on nettoie
            for p in (raw, meta_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
            continue
        found.append((raw, meta_path, sr, dur))
    return found


# --------------------------------------------------------------------------- #
#  Historique — base SQLite
# --------------------------------------------------------------------------- #
# Pourquoi une base et non un gros fichier texte/JSON : l'historique peut grossir
# pendant des années. SQLite (inclus dans Python, zéro dépendance) reste léger, ne
# charge jamais tout en mémoire, permet la suppression ciblée d'une entrée, et borne
# la taille via une purge automatique. Chaque opération ouvre une connexion courte :
# c'est sûr depuis n'importe quel thread (le verrou de fichier SQLite sérialise).
@contextlib.contextmanager
def _hist_db():
    conn = sqlite3.connect(HISTORY_DB, timeout=5.0)
    try:
        with conn:                 # transaction : commit si OK, rollback si exception
            yield conn
    finally:
        conn.close()


def history_init():
    """Crée la table si besoin, l'index de recherche FTS5 (si disponible), puis migre
    une seule fois l'ancien history.json."""
    global _FTS_AVAILABLE
    # 1) Table principale (référence des données) — transaction isolée : elle ne doit
    #    JAMAIS être compromise par un échec de la partie recherche ci-dessous.
    try:
        with _hist_db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS entries ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " ts TEXT NOT NULL,"
                " mode TEXT NOT NULL,"
                " text TEXT NOT NULL)")
    except Exception as e:
        log(f"history_init (table) : {e}")

    # 2) Index de recherche plein-texte (FTS5). Optionnel : si le SQLite embarqué n'a
    #    pas le module FTS5, la création échoue → on continue sans (repli LIKE dans
    #    history_search). L'index « content='entries' » ne duplique pas le texte : il
    #    pointe vers la table. Des déclencheurs le tiennent à jour automatiquement, et
    #    « rebuild » resynchronise l'existant à chaque démarrage (auto-réparation,
    #    négligeable pour ≤ HISTORY_KEEP lignes). tokenize accent-/casse-insensible :
    #    « reunion » trouve « Réunion ».
    try:
        with _hist_db() as conn:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5("
                " text, content='entries', content_rowid='id',"
                " tokenize='unicode61 remove_diacritics 2')")
            conn.execute(
                "CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN"
                " INSERT INTO entries_fts(rowid, text) VALUES (new.id, new.text);"
                " END")
            conn.execute(
                "CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN"
                " INSERT INTO entries_fts(entries_fts, rowid, text)"
                " VALUES('delete', old.id, old.text);"
                " END")
            conn.execute(
                "CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN"
                " INSERT INTO entries_fts(entries_fts, rowid, text)"
                " VALUES('delete', old.id, old.text);"
                " INSERT INTO entries_fts(rowid, text) VALUES (new.id, new.text);"
                " END")
            conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        _FTS_AVAILABLE = True
    except Exception as e:
        _FTS_AVAILABLE = False
        log(f"Recherche FTS5 indisponible (repli sur balayage simple) : {e}")

    # 3) Migration unique de l'ancien history.json. Après la mise en place des
    #    déclencheurs : les lignes migrées sont donc indexées au passage.
    try:
        _history_migrate_json()
    except Exception as e:
        log(f"history_init (migration) : {e}")


def _history_migrate_json():
    """Importe l'ancien history.json (liste) dans la base, puis l'archive en .bak.
    Sécurité des données : on n'archive le fichier QUE si l'import a réussi (ou si la
    liste est légitimement vide). Si le fichier est illisible/corrompu, ou si la base
    contient déjà des entrées non issues de ce fichier, on n'y touche PAS et on
    journalise — aucune donnée perdue, un build ultérieur pourra réessayer."""
    if not os.path.exists(HISTORY_PATH):
        return
    # Lecture directe (pas load_json, qui masquerait une corruption) : on veut voir
    # une erreur de parsing pour NE PAS archiver un fichier qu'on n'a pas su lire.
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log(f"history.json illisible — migration reportée, fichier conservé : {e}")
        return
    if not isinstance(data, list):
        log("history.json inattendu (pas une liste) — conservé, non migré.")
        return
    try:
        if data:
            with _hist_db() as conn:
                already = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                if already != 0:
                    # Base déjà peuplée : on ne fusionne pas et on NE jette PAS le JSON.
                    log("Base d'historique déjà peuplée — history.json conservé, non fusionné.")
                    return
                rows = [(e.get("ts", ""), e.get("mode", "flash"), e.get("text", ""))
                        for e in data if isinstance(e, dict) and e.get("text")]
                conn.executemany(
                    "INSERT INTO entries (ts, mode, text) VALUES (?, ?, ?)", rows)
                log(f"Historique migré depuis history.json : {len(rows)} entrées.")
        # Import réussi (ou liste vide légitime) → on archive le JSON en .bak.
        os.replace(HISTORY_PATH, HISTORY_PATH + ".bak")
    except Exception as e:
        # En cas d'échec d'écriture, la transaction _hist_db a fait un rollback ; on ne
        # renomme pas (l'os.replace n'a pas été atteint), donc le JSON reste en place.
        log(f"migration historique : {e}")


def history_add(mode, text):
    """Ajoute une entrée, purge les plus anciennes, renvoie {id, ts, mode, text}."""
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        with _hist_db() as conn:
            cur = conn.execute(
                "INSERT INTO entries (ts, mode, text) VALUES (?, ?, ?)", (ts, mode, text))
            entry_id = cur.lastrowid
            # Purge : on ne conserve que les HISTORY_KEEP plus récentes (disque borné).
            conn.execute(
                "DELETE FROM entries WHERE id NOT IN "
                "(SELECT id FROM entries ORDER BY id DESC LIMIT ?)", (HISTORY_KEEP,))
        return {"id": entry_id, "ts": ts, "mode": mode, "text": text}
    except Exception as e:
        log(f"history_add : {e}")
        return {"id": None, "ts": ts, "mode": mode, "text": text}


def _history_rows_to_dicts(rows):
    return [{"id": r[0], "ts": r[1], "mode": r[2], "text": r[3]} for r in rows]


def history_recent(limit=15):
    """Les `limit` entrées les plus récentes (la plus récente d'abord)."""
    try:
        with _hist_db() as conn:
            rows = conn.execute(
                "SELECT id, ts, mode, text FROM entries ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        return _history_rows_to_dicts(rows)
    except Exception as e:
        log(f"history_recent : {e}")
        return []


def history_get(entry_id):
    try:
        with _hist_db() as conn:
            r = conn.execute(
                "SELECT id, ts, mode, text FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return {"id": r[0], "ts": r[1], "mode": r[2], "text": r[3]} if r else None
    except Exception as e:
        log(f"history_get : {e}")
        return None


def history_last_meeting():
    try:
        with _hist_db() as conn:
            r = conn.execute(
                "SELECT id, ts, mode, text FROM entries WHERE mode = 'meeting' "
                "ORDER BY id DESC LIMIT 1").fetchone()
        return {"id": r[0], "ts": r[1], "mode": r[2], "text": r[3]} if r else None
    except Exception as e:
        log(f"history_last_meeting : {e}")
        return None


def history_delete(entry_id):
    try:
        with _hist_db() as conn:
            conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return True
    except Exception as e:
        log(f"history_delete : {e}")
        return False


def history_all():
    try:
        with _hist_db() as conn:
            rows = conn.execute(
                "SELECT id, ts, mode, text FROM entries ORDER BY id ASC").fetchall()
        return _history_rows_to_dicts(rows)
    except Exception as e:
        log(f"history_all : {e}")
        return []


def history_clear():
    try:
        with _hist_db() as conn:
            conn.execute("DELETE FROM entries")
        return True
    except Exception as e:
        log(f"history_clear : {e}")
        return False


def history_search(query, limit=30):
    """Recherche plein-texte dans l'historique. Renvoie les entrées correspondantes,
    les plus pertinentes d'abord (FTS5), ou les plus récentes en repli (LIKE)."""
    # On ne garde que les termes contenant au moins un caractère alphanumérique :
    # évite qu'une saisie de ponctuation seule ne produise une requête FTS invalide.
    terms = [t for t in (query or "").split() if any(c.isalnum() for c in t)]
    if not terms:
        return []
    try:
        with _hist_db() as conn:
            if _FTS_AVAILABLE:
                # Chaque terme → un jeton FTS entre guillemets (neutralise la syntaxe
                # spéciale) suffixé de « * » (recherche par préfixe : « bud » → « budget »).
                # Termes multiples = ET implicite (l'entrée doit tous les contenir).
                match = " ".join('"' + t.replace('"', '""') + '"*' for t in terms)
                # L'opérateur MATCH doit porter sur le nom réel de la table FTS (pas un
                # alias, que SQLite prendrait pour une colonne). ORDER BY rank : pertinence.
                rows = conn.execute(
                    "SELECT e.id, e.ts, e.mode, e.text"
                    " FROM entries_fts JOIN entries e ON e.id = entries_fts.rowid"
                    " WHERE entries_fts MATCH ? ORDER BY rank LIMIT ?",
                    (match, limit)).fetchall()
            else:
                # Repli sans FTS5 : chaque terme doit apparaître (ET). ESCAPE protège
                # les jokers « % » et « _ » d'une saisie littérale.
                clauses = " AND ".join(["text LIKE ? ESCAPE '\\'"] * len(terms))
                params = ["%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                          for t in terms]
                rows = conn.execute(
                    "SELECT id, ts, mode, text FROM entries"
                    f" WHERE {clauses} ORDER BY id DESC LIMIT ?",
                    (*params, limit)).fetchall()
        return _history_rows_to_dicts(rows)
    except Exception as e:
        log(f"history_search : {e}")
        return []


# --------------------------------------------------------------------------- #
#  Séparation des locuteurs (diarisation) — sherpa-onnx, optionnel
# --------------------------------------------------------------------------- #
# sherpa-onnx n'est PAS importé au démarrage : c'est une dépendance facultative, absente
# tant que l'utilisateur n'active pas la fonction. On l'importe à la demande, une fois.
_sherpa = None
_sherpa_tried = False


def _load_sherpa():
    """Importe sherpa_onnx à la demande. Renvoie le module ou None (mémorisé : on ne
    retente pas l'import à chaque appel). Réinitialisé après une installation à chaud."""
    global _sherpa, _sherpa_tried
    if _sherpa_tried:
        return _sherpa
    _sherpa_tried = True
    try:
        import sherpa_onnx
        _sherpa = sherpa_onnx
    except Exception as e:
        log(f"sherpa-onnx indisponible : {e}")
        _sherpa = None
    return _sherpa


def diarization_models_present():
    """True si les deux modèles ONNX sont téléchargés."""
    return os.path.exists(DIAR_SEG_PATH) and os.path.exists(DIAR_EMB_PATH)


def diarization_ready():
    """True si la diarisation est utilisable MAINTENANT : modèles présents ET module
    importable. Sert de garde avant chaque tentative (ne casse jamais la transcription)."""
    return diarization_models_present() and _load_sherpa() is not None


def clustering_threshold(duration_s):
    """Seuil de regroupement des voix, croissant avec la durée de l'enregistrement.

    Plus l'enregistrement est long, plus une même voix varie (fatigue, distance au
    micro, sujet), et plus le regroupement automatique la découpe en plusieurs
    locuteurs. Un seuil fixe sur-segmente donc les longues réunions. La montée de
    0,55 à 0,80 entre 15 et 60 minutes vient d'un projet qui utilise exactement la
    même pile que nous (sherpa-onnx + pyannote 3.0) et qui avait observé le cas
    extrême : 46 locuteurs détectés sur 73 minutes.

    Dans sherpa-onnx c'est une DISTANCE : plus le seuil est haut, plus on fusionne.
    Vérifié sur de la vraie parole plutôt que déduit de la documentation (un moteur
    concurrent convertit ce réglage en interne, si bien que l'augmenter y découpe
    DAVANTAGE) : mesures 0,45 → 4 locuteurs, 0,55 → 3, 0,85 → 1 sur un même audio.

    Le plancher reste à 0,50, la valeur utilisée jusqu'ici : sur les enregistrements
    courts aucune sur-segmentation n'a été constatée, et la mesure ne départage pas
    0,50 de 0,55. On ne change donc que ce qui pose réellement problème."""
    low_s, high_s, low_t, high_t = 900.0, 3600.0, 0.50, 0.80
    if duration_s <= low_s:
        return low_t
    if duration_s >= high_s:
        return high_t
    ratio = (duration_s - low_s) / (high_s - low_s)
    return low_t + ratio * (high_t - low_t)


def drop_micro_speakers(diar, min_total=1.0):
    """Supprime les locuteurs qui ne totalisent presque aucune parole, et renumérote.

    Un rire, une sonnerie, une raclement de gorge suffisent à créer un « locuteur »
    fantôme. On écarte ceux qui parlent moins d'une seconde en tout, puis on
    renumérote par ordre de PREMIÈRE prise de parole : « Locuteur 1 » est alors
    vraiment la première personne entendue, ce que l'ordre de sortie du moteur ne
    garantit pas."""
    if not diar:
        return diar
    totals, first = {}, {}
    for start, end, spk in diar:
        totals[spk] = totals.get(spk, 0.0) + max(0.0, end - start)
        if spk not in first or start < first[spk]:
            first[spk] = start
    kept = [s for s, t in totals.items() if t >= min_total]
    if not kept:
        kept = list(totals)                      # jamais tout jeter
    if len(kept) < len(totals):
        log(f"diarisation : {len(totals) - len(kept)} locuteur(s) fantôme(s) écarté(s) "
            f"(moins de {min_total:g} s de parole).")
    order = sorted(kept, key=lambda s: first[s])
    renum = {old: new for new, old in enumerate(order)}
    return [(start, end, renum[spk]) for (start, end, spk) in diar if spk in renum]


def diarize(audio, num_speakers=0, progress=None):
    """Sépare les locuteurs d'un enregistrement (float32 mono 16 kHz normalisé). Renvoie
    une liste de tuples (début_s, fin_s, id_locuteur) triés par début, ou None si
    indisponible/échec. num_speakers : 0 = détection automatique, sinon nombre imposé."""
    so = _load_sherpa()
    if so is None or not diarization_models_present():
        return None
    try:
        threshold = clustering_threshold(len(audio) / 16000.0)
        log(f"diarisation : seuil de regroupement {threshold:.2f} "
            f"({len(audio) / 16000.0 / 60.0:.0f} min d'audio).")
        cfg = so.OfflineSpeakerDiarizationConfig(
            segmentation=so.OfflineSpeakerSegmentationModelConfig(
                pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=DIAR_SEG_PATH)),
            embedding=so.SpeakerEmbeddingExtractorConfig(
                model=DIAR_EMB_PATH, num_threads=CPU_THREADS),
            clustering=so.FastClusteringConfig(
                num_clusters=(num_speakers if num_speakers and num_speakers > 0 else -1),
                threshold=threshold),
            min_duration_on=0.3, min_duration_off=0.5)
        sd = so.OfflineSpeakerDiarization(cfg)
        audio = np.asarray(audio, dtype=np.float32)

        def _cb(*a):
            # sherpa appelle (n_traité, n_total[, arg]) ; on remonte une progression 0-100.
            if progress is not None and len(a) >= 2 and a[1]:
                try:
                    progress(min(100, int(a[0] / a[1] * 100)))
                except Exception:
                    pass
            return 0

        segments = sd.process(audio, callback=_cb).sort_by_start_time()
        return drop_micro_speakers([(s.start, s.end, s.speaker) for s in segments])
    except Exception as e:
        log(f"diarize : {e}")
        return None


def _speaker_at(start, end, diar):
    """Locuteur (int) dont l'intervalle recouvre le plus [start, end].

    Sans recouvrement (passage tombé dans un trou de la segmentation, ou dans la
    plage d'un locuteur fantôme écarté), on se rabat sur la prise de parole la plus
    proche dans le temps. Sans ce repli, ces passages s'affichaient « Locuteur ? »
    et se lisaient comme un participant supplémentaire qui n'existe pas."""
    best, best_ov = None, 0.0
    for d0, d1, spk in diar:
        ov = min(end, d1) - max(start, d0)
        if ov > best_ov:
            best_ov, best = ov, spk
    if best is not None:
        return best
    mid = (start + end) / 2.0
    nearest, nearest_gap = None, None
    for d0, d1, spk in diar:
        gap = 0.0 if d0 <= mid <= d1 else min(abs(mid - d0), abs(mid - d1))
        if nearest_gap is None or gap < nearest_gap:
            nearest_gap, nearest = gap, spk
    return nearest


def format_with_speakers(seglist, diar, timestamps=False, offset=0.0):
    """Assemble le texte en préfixant chaque prise de parole par « — Locuteur N : » quand
    le locuteur change. `seglist` = segments faster-whisper (.start/.end/.text) ; `diar` =
    sortie de diarize() ; `offset` = décalage (s) des segments dans l'audio diarisé. Renvoie
    None si `diar` est vide (l'appelant garde alors le rendu habituel)."""
    if not diar:
        return None
    lines = []
    current = object()   # sentinelle : garantit un en-tête au tout premier segment
    for s in seglist:
        txt = s.text.strip()
        if not txt:
            continue
        spk = _speaker_at(s.start + offset, s.end + offset, diar)
        if spk != current:
            current = spk
            label = f"Locuteur {spk + 1}" if spk is not None else "Locuteur ?"
            if lines:
                lines.append("")          # ligne vide entre deux locuteurs (lisibilité)
            lines.append(f"— {label} :")
        prefix = f"[{fmt_ts(s.start + offset)}] " if timestamps else ""
        lines.append(f"{prefix}{txt}")
    return "\n".join(lines).strip()


# --------------------------------------------------------------------------- #
#  Application
# --------------------------------------------------------------------------- #
class VoixFlashApp(rumps.App):
    def __init__(self):
        # quit_button=None : on fournit notre propre bouton "Quitter" plus bas.
        # On ne met PAS de titre texte : l'état est montré par une icône (cf. plus bas).
        super().__init__(APP_NAME, title=None, quit_button=None)

        # Indicateur "chargement" dès le départ (micro fin, en blanc comme les natifs).
        self._symbol_cache = {}
        self._apply_state_icon("loading")

        # Cacher l'icône du Dock (présence discrète, uniquement barre des menus).
        if NSApplication is not None:
            try:
                NSApplication.sharedApplication().setActivationPolicy_(
                    NSApplicationActivationPolicyAccessory
                )
            except Exception as e:
                log(f"activation policy: {e}")

        # Première exécution ? (sert à afficher l'aide une seule fois)
        first_run = not os.path.exists(CONFIG_PATH)

        # Réglages persistants. L'historique, lui, vit dans une base SQLite (history_init).
        self.config = {**DEFAULT_CONFIG, **load_json(CONFIG_PATH, {})}
        history_init()

        # État interne
        self.model = None                 # le moteur de transcription, chargé en fond
        self.model_name_loaded = None     # nom du modèle actuellement en mémoire
        self._requested_model = self.config["model"]  # dernier modèle DEMANDÉ (le plus récent gagne)
        self._state = "loading"
        self._recording = False
        # Une transcription est-elle EN COURS (réunion/dictée OU import de fichier) ? Le
        # moteur CTranslate2 n'est pas réentrant : deux transcriptions simultanées le feraient
        # planter. Ce drapeau unifié interdit tout chevauchement (cf. _process_audio, _run_import).
        self._transcribing = False
        self._importing = False           # un import de FICHIER est-il en cours ? (≠ réunion)
        self._import_cancel = False       # demande d'annulation de l'import en cours
        self._transcribing_meeting = False  # la transcription en cours est-elle une RÉUNION ?
        self._transcribe_cancel = False   # demande d'annulation de la transcription de réunion
        self._record_mode = None          # "flash" ou "meeting"
        self._ptt_active = False          # touche de dictée actuellement maintenue ?
        self._ptt_started = None          # instant d'appui (mesure des appuis trop brefs)
        self._capturing = False           # en train de capturer une nouvelle touche ?
        self._sounds = Sounds()           # lecteurs préparés une fois pour toutes
        self._wake_observer = None        # abonnement au réveil du Mac
        self._need_rearm = False          # réarmement de l'écoute à faire dès que possible
        self._captured = None             # dernière touche captée pendant la capture
        self._stream = None               # flux audio en cours
        self._frames = []                 # morceaux audio enregistrés
        self._record_sr = 16000           # fréquence d'échantillonnage utilisée
        self._record_start = None         # début de l'enregistrement (garde-fou durée)
        self._last_listener_restart = 0.0  # anti-rafale pour la relance de l'écoute
        self._ui_queue = queue.Queue()    # messages des threads de fond vers l'UI
        self._deferred = []               # messages d'UI en attente d'un moment sûr
        # Sauvegarde disque de la réunion en cours (cf. _start_disk_backup).
        self._disk_queue = None           # file d'écriture (audio → thread d'écriture)
        self._disk_thread = None          # thread qui écrit le fichier brut
        self._disk_paths = None           # (raw, json) de la sauvegarde en cours
        self._lock = threading.Lock()
        # Restauration du presse-papiers après un collage (cf. _paste_text). La
        # « génération » sert aux dictées enchaînées : seule la plus récente a le
        # droit de restaurer, et c'est TOUJOURS le presse-papiers d'origine de
        # l'utilisateur qui est restauré, jamais le texte de la dictée précédente.
        self._pb_lock = threading.Lock()
        self._pb_gen = 0
        self._pb_pending = None           # (génération, instantané, changeCount à nous)
        self._hotkey = parse_hotkey(self.config["hotkey"])
        self._listener = None

        # Construction du menu
        self._build_menu()

        # Le minuteur tourne sur le thread principal : c'est LUI (et lui seul) qui
        # touche à l'interface, à partir des messages déposés par les threads de fond.
        # 0,15 s = indicateur réactif, et coût processeur négligeable au repos.
        self._timer = rumps.Timer(self._drain_ui, 0.15)
        self._timer.start()
        self._install_timer_common_modes()

        # Chargement du modèle en arrière-plan → démarrage instantané de l'app.
        threading.Thread(target=self._load_model, daemon=True).start()

        # Amorce du micro (une seule fois) : ouvre brièvement l'entrée audio pour
        # DÉCLENCHER la demande d'autorisation macOS. Sans ça, « Python » n'apparaît
        # jamais dans Réglages › Confidentialité › Microphone et reste impossible à cocher.
        threading.Thread(target=self._prime_microphone, daemon=True).start()

        # Écoute clavier globale pour la dictée éclair.
        self._start_listener()
        self._install_wake_observer()

        # Garde-fous de sécurité sur un thread DÉDIÉ (et non plus sur le minuteur d'UI).
        # Raison : une fenêtre modale (alerte, fenêtre de réunion) fige le thread
        # principal, donc le minuteur. Si les garde-fous en dépendaient, l'arrêt
        # automatique d'un enregistrement emballé et la relance de l'écoute clavier
        # cesseraient de fonctionner tant qu'un dialogue est ouvert. Ce thread, lui,
        # continue de tourner. Il ne touche JAMAIS l'UI directement : il passe par la file.
        threading.Thread(target=self._watchdog_loop, daemon=True).start()

        # Sauvegarde initiale de la config (crée le fichier).
        save_json(CONFIG_PATH, self.config)

        # Au tout premier lancement, on affiche l'aide sur les autorisations.
        if first_run:
            self._ui_queue.put(("welcome", None))

        # Une réunion a-t-elle été interrompue (fermeture forcée, plante, coupure) ?
        # Son audio est sur le disque : on propose de la transcrire maintenant.
        interrupted = find_interrupted_meetings()
        if interrupted:
            log(f"{len(interrupted)} réunion(s) interrompue(s) retrouvée(s) sur le disque.")
            self._ui_queue.put(("recover_meeting", interrupted))

        log(f"{APP_NAME} {APP_VERSION} démarré (modèle demandé : {self._requested_model}).")

    # ----------------------------------------------------------------- menu --
    def _build_menu(self):
        self.meeting_item = rumps.MenuItem(MEETING_START_TITLE, callback=self.toggle_meeting)
        self.history_menu = rumps.MenuItem("Historique récent")
        # Recherche dans l'historique : item de saisie + sous-menu de résultats cliquables.
        # L'état de la dernière recherche est conservé pour survivre aux reconstructions
        # du menu d'historique (cf. _fill_search_results).
        self.search_item = rumps.MenuItem("🔍 Rechercher…", callback=self.search_history)
        self.search_results_menu = rumps.MenuItem("Résultats de recherche")
        self._search_query = None
        self._search_results = []
        self.reunions_menu = rumps.MenuItem("Réunions")
        self.quality_menu = rumps.MenuItem("Qualité / vitesse")
        self.lang_menu = rumps.MenuItem("Langue")
        self.hotkey_menu = rumps.MenuItem("Touche de dictée")
        self.ts_item = rumps.MenuItem("Horodatage des passages", callback=self.toggle_timestamps)
        self.restore_item = rumps.MenuItem("Restaurer le presse-papiers après une dictée",
                                           callback=self.toggle_restore)
        self.text_menu = rumps.MenuItem("Texte dicté")
        self.hesit_item = rumps.MenuItem("Retirer les hésitations (euh, hmm)",
                                         callback=self.toggle_hesitations)
        self.sound_item = rumps.MenuItem("Retour sonore (début et fin de dictée)",
                                         callback=self.toggle_sounds)
        self.help_menu = rumps.MenuItem("Aide & autorisations")

        self.menu = [
            self.meeting_item,
            rumps.separator,
            self.history_menu,
            rumps.separator,
            self.reunions_menu,
            self.quality_menu,
            self.lang_menu,
            self.text_menu,
            self.hotkey_menu,
            self.sound_item,
            self.restore_item,
            rumps.separator,
            self.help_menu,
            rumps.MenuItem("Redémarrer VoixFlash", callback=self.restart_app),
            rumps.MenuItem("Quitter", callback=self.quit_app),
        ]

        # Sous-menu « Réunions » : actions et réglages propres aux réunions.
        # « Importer un fichier audio… » : transcrit un fichier existant (ou la piste audio
        # d'une vidéo) exactement comme une réunion. L'item bascule en « Annuler… » pendant
        # le traitement (cf. import_audio_file / _run_import).
        # Sous-menu « Texte dicté » : vocabulaire de l'utilisateur et nettoyage. Le
        # vocabulaire est appliqué APRÈS la transcription (cf. postprocess_text).
        self.text_menu.add(rumps.MenuItem("Ajouter un mot au vocabulaire…",
                                          callback=self.vocab_add_word))
        self.text_menu.add(rumps.MenuItem("Corriger une faute récurrente…",
                                          callback=self.vocab_add_correction))
        self.text_menu.add(rumps.MenuItem("Ouvrir le fichier de vocabulaire…",
                                          callback=self.vocab_open_file))
        self.text_menu.add(rumps.separator)
        self.text_menu.add(self.hesit_item)

        self.import_item = rumps.MenuItem(IMPORT_IDLE_TITLE, callback=self.import_audio_file)
        self.reunions_menu.add(self.import_item)
        self.reunions_menu.add(rumps.MenuItem("Exporter la dernière réunion (.txt)",
                                              callback=self.export_last_meeting))
        self.reunions_menu.add(self.ts_item)
        # Séparation des locuteurs : bascule (installe le module à la 1re activation) +
        # sous-menu « Locuteurs attendus ». Placés sous une séparation pour les distinguer.
        self.reunions_menu.add(rumps.separator)
        self.diar_item = rumps.MenuItem("Séparer les locuteurs (réunions)",
                                        callback=self.toggle_diarization)
        self.reunions_menu.add(self.diar_item)
        self.diar_speakers_menu = rumps.MenuItem("Locuteurs attendus")
        self.reunions_menu.add(self.diar_speakers_menu)
        self._diar_installing = False

        # Remplissage des sous-menus
        self._refresh_quality_menu()
        self._refresh_lang_menu()
        self._refresh_hotkey_menu()
        self._refresh_history_menu()
        self._refresh_diar_menu()
        self.ts_item.state = bool(self.config["meeting_timestamps"])
        self.restore_item.state = bool(self.config["restore_clipboard"])
        self.hesit_item.state = bool(self.config.get("remove_hesitations", True))
        self.sound_item.state = bool(self.config.get("sounds_enabled", True))

        # Sous-menu d'aide : guide complet en tête, puis liens vers les réglages macOS.
        self.help_menu.add(rumps.MenuItem("Mode d'emploi complet", callback=self.show_guide))
        self.help_menu.add(rumps.MenuItem("La touche de dictée ne répond plus ?",
                                          callback=self.diagnose_hotkey))
        self.help_menu.add(rumps.MenuItem("Voir le chemin à autoriser", callback=self.show_path))
        self.help_menu.add(rumps.MenuItem("Ouvrir réglages › Microphone", callback=self.open_mic_settings))
        self.help_menu.add(rumps.MenuItem("Ouvrir réglages › Accessibilité", callback=self.open_acc_settings))
        self.help_menu.add(rumps.MenuItem("Ouvrir réglages › Surveillance des entrées", callback=self.open_input_settings))

    @staticmethod
    def _safe_clear(menu):
        # Au tout premier build (depuis __init__), le sous-menu n'a pas encore de
        # NSMenu interne : son attribut _menu vaut None et .clear() planterait avec
        # "AttributeError: 'NoneType' object has no attribute 'removeAllItems'".
        # On ne vide donc que les sous-menus déjà construits.
        if getattr(menu, "_menu", None) is not None:
            menu.clear()

    def _refresh_quality_menu(self):
        self._safe_clear(self.quality_menu)
        for label, val in MODEL_CHOICES:
            item = rumps.MenuItem(label, callback=self._make_quality_cb(val))
            item.state = (self.config["model"] == val)
            self.quality_menu.add(item)

    def _refresh_lang_menu(self):
        self._safe_clear(self.lang_menu)
        for label, val in [("Français", "fr"), ("Anglais", "en"), ("Automatique (détection)", "auto")]:
            item = rumps.MenuItem(label, callback=self._make_lang_cb(val))
            item.state = (self.config["language"] == val)
            self.lang_menu.add(item)

    def _refresh_hotkey_menu(self):
        self._safe_clear(self.hotkey_menu)
        current = self.config.get("hotkey", "alt_r")
        is_preset = any(current == v for _, v in HOTKEY_CHOICES)
        for label, val in HOTKEY_CHOICES:
            item = rumps.MenuItem(label, callback=self._make_hotkey_cb(val))
            item.state = (current == val)
            self.hotkey_menu.add(item)
        self.hotkey_menu.add(rumps.separator)
        # « Choisir ma touche… » : capture la prochaine touche pressée. Coché si la
        # touche active est une touche personnalisée (donc hors préréglages).
        if is_preset:
            cap_title = "Choisir ma touche…"
        else:
            cap_title = f"Ma touche : {self._current_hotkey_label()}  (changer…)"
        cap = rumps.MenuItem(cap_title, callback=self.start_hotkey_capture)
        cap.state = not is_preset
        self.hotkey_menu.add(cap)

    def _refresh_history_menu(self):
        """Reconstruit le sous-menu d'historique : entrées récentes cliquables (→ fenêtre
        de transcription), puis export et vidage. À appeler sur le thread principal."""
        self._safe_clear(self.history_menu)
        # Recherche en tête : champ de saisie + sous-menu des résultats (reconstruit à
        # partir de la dernière recherche pour survivre à ce rafraîchissement).
        self.history_menu.add(self.search_item)
        self.history_menu.add(self.search_results_menu)
        self._fill_search_results()
        self.history_menu.add(rumps.separator)
        recent = history_recent(15)   # les 15 plus récentes (la plus récente d'abord)
        if not recent:
            self.history_menu.add(rumps.MenuItem("(vide)"))
        else:
            for i, entry in enumerate(recent):
                preview = " ".join((entry.get("text") or "").split())
                if len(preview) > 44:
                    preview = preview[:44] + "…"
                tag = "Réunion" if entry.get("mode") == "meeting" else "Dictée"
                # Le numéro garantit un titre unique (les menus rumps sont indexés par titre).
                title = f"{i + 1}.  {tag} · {preview}"
                self.history_menu.add(rumps.MenuItem(title, callback=self._make_history_cb(entry["id"])))
        self.history_menu.add(rumps.separator)
        self.history_menu.add(rumps.MenuItem("Exporter tout l'historique (.txt)",
                                             callback=self.export_all_history))
        self.history_menu.add(rumps.MenuItem("Vider l'historique…", callback=self.clear_history))

    # ------------------------------------------------- fabriques de callbacks --
    def _model_label(self, val):
        for label, v in MODEL_CHOICES:
            if v == val:
                return label
        return val

    def _make_quality_cb(self, val):
        def cb(_sender):
            self.config["model"] = val
            save_json(CONFIG_PATH, self.config)
            self._refresh_quality_menu()
            # On note le DERNIER modèle demandé : si on reclique vite sur un autre, le
            # chargement en cours sera ignoré à la fin (le plus récent gagne), et on
            # évite d'écraser self.model par un modèle obsolète ou d'empiler des alertes.
            with self._lock:
                self._requested_model = val
            # Si le modèle n'est pas encore téléchargé, on prévient : c'est l'attente
            # « longue » (jusqu'à ~1 min) qui surprenait. Sinon (déjà en cache), le
            # chargement est rapide et l'icône suffit comme retour.
            if not model_is_cached(val):
                self._present(
                    self._show_info, "Téléchargement du modèle",
                    f"Le modèle « {self._model_label(val)} » se télécharge (1re fois, "
                    "jusqu'à ~1 min selon ta connexion). L'icône micro se remplit quand "
                    "c'est prêt — tu peux continuer à travailler. Ensuite, c'est hors-ligne.")
            # On passe le nom explicitement (pas via la config, qui peut changer) et
            # announce=True : on confirme « prêt » à la fin (changement demandé par
            # l'utilisateur ; au démarrage on reste muet).
            threading.Thread(target=self._load_model, kwargs={"name": val, "announce": True},
                             daemon=True).start()
        return cb

    def _make_lang_cb(self, val):
        def cb(_sender):
            self.config["language"] = val
            save_json(CONFIG_PATH, self.config)
            self._refresh_lang_menu()
        return cb

    def _make_hotkey_cb(self, val):
        def cb(_sender):
            # IMPORTANT : ne JAMAIS recréer l'écoute pynput depuis un callback de menu.
            # Stop()+start() d'un event tap Quartz sur le thread principal d'une app
            # Cocoa fait planter l'application. Inutile, d'ailleurs : l'écoute capte
            # déjà TOUTES les touches et les compare à self._hotkey à chaque appui. Il
            # suffit donc de changer la cible « à chaud ».
            try:
                label = self._hotkey_label(val)
                self.config["hotkey"] = val
                self.config["hotkey_label"] = label
                save_json(CONFIG_PATH, self.config)
                self._hotkey = parse_hotkey(val)
                self._ptt_active = False
                self._refresh_hotkey_menu()
                # Retour RÉELLEMENT visible (les notifications macOS ne marchent pas hors
                # bundle) : on ouvre l'alerte au tour de boucle suivant pour ne pas la
                # déclencher pendant que le menu est encore en cours de fermeture.
                self._present(self._show_info, "Touche changée",
                              f"Dictée éclair : {label}")
            except Exception as e:
                log(f"changement de touche : {e}")
        return cb

    def _hotkey_label(self, val):
        for label, v in HOTKEY_CHOICES:
            if v == val:
                return label
        return val

    def _current_hotkey_label(self):
        """Libellé de la touche de dictée ACTUELLE (préréglage ou touche capturée)."""
        val = self.config.get("hotkey", "alt_r")
        for label, v in HOTKEY_CHOICES:
            if v == val:
                return label
        return self.config.get("hotkey_label") or val

    def start_hotkey_capture(self, _sender):
        """« Appuie sur ta touche » : capture la prochaine touche pressée et en fait la
        touche de dictée. Comme on capte ce que CE clavier émet réellement, la touche
        correspondra toujours ensuite (fini les soucis Option droite = alt_r ou alt_gr
        selon la machine). Si rien n'est capté, c'est le signe que « Surveillance des
        entrées » n'est pas autorisée → on le diagnostique et on propose de l'ouvrir."""
        self._captured = None
        self._capturing = True
        validated = self._modal_alert(
            title="Choisir la touche de dictée",
            message="Appuie MAINTENANT sur la touche que tu veux utiliser pour la "
                    "dictée éclair (idéalement une touche de fonction comme F6, ou un "
                    "modificateur comme Option), puis clique « Valider » à la souris.\n\n"
                    "Astuce : évite une lettre normale — tu l'écrirais en dictant.",
            ok="Valider", cancel="Annuler",
        )
        self._capturing = False
        key = self._captured
        self._captured = None

        if validated != 1:                # Annuler
            return
        if key is None:
            # Aucune touche reçue : très probablement « Surveillance des entrées » non
            # accordée (l'écoute clavier ne reçoit alors RIEN). On guide l'utilisateur.
            if self._confirm(
                    "Aucune touche détectée.\n\nSoit tu n'as pas appuyé, soit "
                    "l'autorisation « Surveillance des entrées » manque pour VoixFlash "
                    "(il apparaît sous le nom « Python »).\n\nOuvrir ce réglage maintenant ?",
                    ok="Ouvrir le réglage", cancel="Plus tard"):
                self.open_input_settings(None)
            return

        serialized = serialize_hotkey(key)
        if not serialized:
            self._show_error("Touche non reconnue, réessaie avec une autre touche.")
            return
        label = hotkey_display(key)
        self.config["hotkey"] = serialized
        self.config["hotkey_label"] = label
        save_json(CONFIG_PATH, self.config)
        self._hotkey = parse_hotkey(serialized)
        self._ptt_active = False
        self._refresh_hotkey_menu()

        # Avertissement doux si la touche produit aussi un caractère (risque de l'écrire).
        note = ""
        if not isinstance(key, keyboard.Key) and getattr(key, "char", None):
            note = ("\n\n⚠ Cette touche écrit aussi un caractère : tu risques de l'insérer "
                    "en dictant. Une touche de fonction (F6…) serait plus sûre.")
        self._show_info("Touche réglée", f"Dictée éclair : {label} ✓{note}")

    def _make_history_cb(self, entry_id):
        """Clic sur une entrée d'historique → ouvre sa fenêtre de transcription."""
        def cb(_sender):
            entry = history_get(entry_id)
            if entry is None:
                self._present(self._show_error, "Cette entrée n'existe plus.")
                return
            self._present(self._show_transcript, entry)
        return cb

    # ------------------------------------------------------ recherche historique --
    def _fill_search_results(self, entry_ids=None):
        """(Re)construit le sous-menu « Résultats de recherche » à partir de la dernière
        recherche. Appelé après une recherche ET à chaque reconstruction de l'historique
        (le menu parent est vidé/reconstruit, mais l'état de recherche persiste).
        Thread principal."""
        self._safe_clear(self.search_results_menu)
        if not self._search_query:
            self.search_results_menu.add(rumps.MenuItem("(aucune recherche)"))
            return
        n = len(self._search_results)
        # En-tête non cliquable (pas de callback → grisé) : rappelle la requête et le compte.
        self.search_results_menu.add(rumps.MenuItem(f"« {self._search_query} » — {n} résultat·s"))
        if not self._search_results:
            return
        self.search_results_menu.add(rumps.separator)
        for i, entry in enumerate(self._search_results):
            preview = " ".join((entry.get("text") or "").split())
            if len(preview) > 44:
                preview = preview[:44] + "…"
            tag = "Réunion" if entry.get("mode") == "meeting" else "Dictée"
            # Le numéro garantit un titre unique (menus rumps indexés par titre).
            title = f"{i + 1}.  {tag} · {preview}"
            self.search_results_menu.add(
                rumps.MenuItem(title, callback=self._make_history_cb(entry["id"])))

    def search_history(self, _sender):
        """Item « 🔍 Rechercher… » : saisit des mots-clés, cherche dans l'historique, et
        remplit le sous-menu « Résultats de recherche » (cliquable → fenêtre de
        transcription). Callback de menu → thread principal : la fenêtre modale est
        légitime ici (comme rumps.alert / le sélecteur de fichier)."""
        try:
            app_to_front()
            win = rumps.Window(
                title="Rechercher dans l'historique",
                message="Tape un ou plusieurs mots-clés, puis « Chercher ».\n"
                        "Plusieurs mots = toutes les entrées qui les contiennent tous.\n"
                        "Les résultats apparaissent dans le sous-menu « Résultats de recherche ».",
                ok="Chercher",
                cancel="Annuler",
                dimensions=(300, 22),
            )
            resp = win.run()
        except Exception as e:
            log(f"search_history (fenêtre) : {e}")
            return
        # Le bouton OK (« Chercher ») vaut clicked == 1 (cf. _show_transcript) ; toute
        # autre valeur = Annuler / Échap → on abandonne sans rien changer.
        if resp.clicked != 1:
            return
        query = " ".join((resp.text or "").split())
        if not query:
            self._show_info("Recherche vide", "Aucun mot-clé saisi.")
            return
        results = history_search(query)
        self._search_query = query
        self._search_results = results
        self._fill_search_results()
        if results:
            self._show_info(
                "Résultats de recherche",
                f"{len(results)} résultat·s pour « {query} ».\n\n"
                "Ouvre le menu VoixFlash › « Historique récent » › "
                "« Résultats de recherche ».")
        else:
            self._show_info("Aucun résultat",
                            f"Aucune entrée d'historique ne contient « {query} ».")

    # ----------------------------------------------------- icône d'état (barre) --
    def _symbol_image(self, symbol_name):
        """Construit une image « template » à partir d'un symbole SF (cache mémoire).
        Renvoie None si les symboles SF ne sont pas disponibles (vieux macOS)."""
        if symbol_name in self._symbol_cache:
            return self._symbol_cache[symbol_name]
        img = None
        try:
            from AppKit import NSImage
            img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol_name, APP_NAME)
            if img is not None:
                # Taille adaptée à la barre des menus (≈ 15-18 px de haut selon le glyphe).
                try:
                    from AppKit import NSImageSymbolConfiguration
                    cfg = NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(13.0, 0.0, 2)
                    sized = img.imageWithSymbolConfiguration_(cfg)
                    if sized is not None:
                        img = sized
                except Exception:
                    pass
                img.setTemplate_(True)   # → rendu blanc/noir comme les icônes natives
        except Exception as e:
            log(f"symbole « {symbol_name} » : {e}")
            img = None
        self._symbol_cache[symbol_name] = img
        return img

    def _apply_state_icon(self, state):
        """Affiche l'état via une icône monochrome native (repli : emoji en titre)."""
        img = self._symbol_image(STATE_SYMBOLS.get(state, "mic.fill"))
        if img is not None:
            self._icon_nsimage = img
            try:
                self._nsapp.setStatusBarIcon()   # mise à jour live si la barre existe déjà
            except AttributeError:
                pass                             # avant run() : sera pris au démarrage
            self.title = None                    # pas de texte à côté de l'icône
        else:
            # Aucun symbole SF disponible : on retombe sur l'emoji historique.
            self.title = STATE_TITLES.get(state, "")

    # ------------------------------------------------------- autorisation micro --
    def _prime_microphone(self, force=False):
        """Ouvre brièvement le micro pour déclencher la demande d'autorisation macOS,
        ce qui inscrit VoixFlash dans Réglages › Confidentialité › Microphone. Fait une
        seule fois (drapeau mic_primed) pour ne pas allumer la pastille micro à chaque
        démarrage ; `force=True` permet de relancer la demande depuis le menu d'aide."""
        if not force and self.config.get("mic_primed"):
            return
        try:
            s = sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                               callback=lambda *a: None)
            s.start()
            time.sleep(0.15)
            s.stop()
            s.close()
            log("Micro amorcé (demande d'autorisation déclenchée).")
        except Exception as e:
            # Même un échec inscrit l'app dans la liste « Microphone » (en refusé) :
            # l'utilisateur peut alors l'activer à la main. On ne retente donc pas en boucle.
            log(f"amorce micro : {e}")
        self.config["mic_primed"] = True
        save_json(CONFIG_PATH, self.config)

    # --------------------------------------------------------- modèle Whisper --
    def _load_model(self, name=None, announce=False):
        """Charge (ou recharge) le moteur de transcription, en arrière-plan.
        name : modèle à charger (par défaut celui de la config, pour le démarrage).
        announce=True : informe l'utilisateur quand le modèle est prêt (changement
        demandé via le menu) ; au démarrage on reste silencieux."""
        if name is None:
            name = self.config["model"]
        self._ui_queue.put(("state", "loading"))
        try:
            # device="cpu" et compute_type="int8" : impératif sur Apple Silicon
            # (jamais le GPU/mps), rapide et léger en mémoire.
            #
            # IMPORTANT — chargement HORS-LIGNE en priorité. Par défaut, faster-whisper
            # contacte Hugging Face pour « vérifier » le modèle même quand il est déjà
            # en cache. Si le réseau bloque (route IPv6 vers le CDN HF qui reste en
            # SYN_SENT, ou requêtes anonymes étranglées), ce contrôle PEND indéfiniment
            # et l'app reste coincée sur « chargement ». Or l'app est hors-ligne par
            # conception : on charge donc d'abord depuis le cache, SANS aucun réseau.
            # cpu_threads bridé (CPU_THREADS = cœurs - 2) : la transcription ne monopolise
            # plus tous les cœurs, donc la machine reste utilisable pendant un long traitement
            # (réunions ET imports de fichiers en profitent).
            try:
                model = WhisperModel(name, device="cpu", compute_type="int8",
                                     cpu_threads=CPU_THREADS, local_files_only=True)
                log(f"Modèle chargé depuis le cache : {name}")
            except Exception as cache_miss:
                # Modèle pas encore téléchargé (tout premier usage de cette qualité) :
                # on autorise alors le téléchargement réseau, une seule fois.
                # ⚠ On vérifie D'ABORD que le réseau répond. Sans ce contrôle, une
                # connexion qui pend (portail captif, VPN, route IPv6 morte) laissait
                # l'app coincée sur « chargement » indéfiniment, sans message.
                log(f"Modèle « {name} » absent du cache ({cache_miss}) — téléchargement…")
                if not internet_reachable():
                    raise RuntimeError(
                        "le modèle n'est pas encore téléchargé et internet ne répond "
                        "pas. Connecte-toi, puis choisis « Redémarrer VoixFlash ». "
                        "Astuce : une qualité déjà téléchargée reste utilisable "
                        "hors-ligne (menu « Qualité / vitesse »)")
                model = WhisperModel(name, device="cpu", compute_type="int8",
                                     cpu_threads=CPU_THREADS)
                log(f"Modèle téléchargé puis chargé : {name}")
            # On ne « commit » le modèle QUE s'il est toujours celui demandé : si
            # l'utilisateur a recliqué sur une autre qualité entre-temps, ce chargement
            # est obsolète → on l'abandonne (pas d'écrasement, pas d'alerte « prêt »).
            committed = False
            with self._lock:
                if name == self._requested_model:
                    self.model = model
                    self.model_name_loaded = name
                    committed = True
            if committed and announce:
                self._ui_queue.put(("info", ("Modèle prêt",
                                             f"« {self._model_label(name)} » est chargé. ✓")))
            elif not committed:
                log(f"Chargement de « {name} » abandonné : « {self._requested_model} » demandé entre-temps.")
        except Exception as e:
            log(f"Erreur de chargement du modèle '{name}' : {e}")
            self._ui_queue.put(("error", f"Impossible de charger le modèle « {name} » : {e}"))
        finally:
            # On ne remet « prêt » (icône pleine) que pour le chargement courant : un
            # chargement obsolète ne doit pas faire croire que tout est prêt alors que
            # le bon modèle se charge encore.
            if not self._recording and name == self._requested_model:
                self._ui_queue.put(("state", "idle"))

    # --------------------------------------------------------- écoute clavier --
    def _install_wake_observer(self):
        """S'abonne au réveil du Mac pour réarmer l'écoute clavier (cf. _on_wake)."""
        if WakeObserver is None:
            return
        try:
            from AppKit import NSWorkspace
            self._wake_observer = WakeObserver.alloc().initWithCallback_(self._on_wake)
            NSWorkspace.sharedWorkspace().notificationCenter(
            ).addObserver_selector_name_object_(
                self._wake_observer, b"onWake:", "NSWorkspaceDidWakeNotification", None)
            log("Réarmement au réveil : observateur installé.")
        except Exception as e:
            log(f"observateur de réveil : {e}")

    def _on_wake(self):
        """Réarme l'écoute clavier quand le Mac sort de veille.

        macOS invalide la prise d'événements clavier pendant la veille, MAIS le
        thread d'écoute reste vivant : le garde-fou qui surveille sa mort ne voit
        donc rien, et la touche de dictée reste muette jusqu'au prochain
        redémarrage de l'app. C'est le scénario « mon Mac a dormi cette nuit et ce
        matin la dictée ne marche plus ».

        Le réarmement ne doit JAMAIS démarrer ni arrêter un enregistrement : s'il y
        en a un en cours, on se contente de noter qu'il faudra réarmer plus tard."""
        if self._recording or self._ptt_active:
            self._need_rearm = True
            return
        # Court délai : au retour de veille, les services système ne sont pas
        # encore tous revenus, et un réarmement immédiat retombe sur une prise
        # d'événements tout aussi morte.
        threading.Timer(1.0, self._rearm_listener, args=("réveil du Mac",)).start()

    def _rearm_listener(self, reason):
        """Recrée l'écoute clavier. Sûr hors du thread principal."""
        try:
            self._need_rearm = False
            log(f"Réarmement de l'écoute clavier ({reason}).")
            self._start_listener()
        except Exception as e:
            log(f"réarmement de l'écoute : {e}")

    def _start_listener(self):
        """(Re)démarre l'écoute clavier globale pour la dictée éclair."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
        self._ptt_active = False          # on repart d'un état propre
        self._hotkey = parse_hotkey(self.config["hotkey"])
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def _on_press(self, key):
        # IMPORTANT : aucune exception ne doit sortir d'un callback pynput, sinon
        # l'écoute clavier meurt et la dictée ne marche plus du tout.
        try:
            # Mode capture : on mémorise la touche pressée (la dernière gagne) et on
            # ne déclenche surtout pas d'enregistrement.
            if self._capturing:
                self._captured = key
                return
            if self._ptt_active:
                if key_matches(key, self._hotkey):
                    return        # répétition automatique de la touche maintenue
                # Une AUTRE touche arrive pendant le maintien.
                if key == keyboard.Key.esc:
                    self._cancel_recording("annulée (Échap)")
                    return
                # Avec un modificateur comme touche de dictée, « Option + A » n'est pas
                # une dictée : c'est un raccourci que l'utilisateur voulait taper. On
                # jette la capture au lieu de coller le bruit qui l'accompagne.
                if hotkey_is_modifier(self._hotkey) and not hotkey_is_modifier(key):
                    self._cancel_recording("annulée (accord de touches)")
                return
            if not key_matches(key, self._hotkey):
                return
            if self._recording:               # une réunion est déjà en cours
                return
            if self._transcribing:            # un import/une transcription tourne déjà
                self._ui_queue.put(("error", "Une transcription est déjà en cours, réessaie dans un instant."))
                return
            if self.model is None:            # le moteur n'est pas encore prêt
                self._ui_queue.put(("error", "Le moteur de transcription se charge encore, réessaie dans un instant."))
                return
            self._ptt_active = True
            self._ptt_started = time.monotonic()
            self._start_recording("flash")
        except Exception as e:
            log(f"_on_press : {e}")
            self._ptt_active = False

    def _on_release(self, key):
        try:
            if self._capturing:
                return
            if not self._ptt_active:
                return
            if not key_matches(key, self._hotkey):
                return
            self._ptt_active = False
            held = time.monotonic() - (self._ptt_started or 0.0)
            # Appui trop bref pour être une dictée : on jette. Réservé aux touches
            # MODIFICATRICES, qu'on effleure souvent sans intention. Appliquée à une
            # touche ordinaire, cette règle jetterait de vraies dictées : l'utilisateur
            # peut relâcher la touche aussitôt et continuer à parler.
            if hotkey_is_modifier(self._hotkey) and held < SHORT_TAP_S:
                self._cancel_recording(f"ignorée (appui de {held * 1000:.0f} ms)")
                return
            if self.config.get("sounds_enabled", True):
                self._sounds.play("stop")
            self._stop_recording()
        except Exception as e:
            log(f"_on_release : {e}")
            self._ptt_active = False

    # -------------------------------------- sauvegarde disque d'une réunion --
    def _start_disk_backup(self, sr):
        """Ouvre la sauvegarde au fil de l'eau d'une réunion (PCM 16 bits mono brut).

        L'écriture se fait dans un thread DÉDIÉ, alimenté par une file : le callback
        audio de PortAudio tourne sur un thread temps réel, où une écriture disque
        bloquante provoquerait des trous dans l'enregistrement."""
        try:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            raw_path, meta_path = meeting_backup_paths(stamp)
            save_json(meta_path, {"sr": int(sr), "started": stamp, "version": APP_VERSION})
            q = queue.Queue()
            t = threading.Thread(target=self._disk_writer_loop, args=(raw_path, q), daemon=True)
            self._disk_queue = q
            self._disk_thread = t
            self._disk_paths = (raw_path, meta_path)
            t.start()
            log(f"Sauvegarde de réunion ouverte : {os.path.basename(raw_path)} ({sr} Hz)")
        except Exception as e:
            # Une sauvegarde impossible ne doit JAMAIS empêcher d'enregistrer.
            log(f"ouverture de la sauvegarde de réunion : {e}")
            self._disk_queue = self._disk_thread = self._disk_paths = None

    @staticmethod
    def _disk_writer_loop(raw_path, q):
        """Écrit les blocs audio au fil de l'eau jusqu'au message de fin (None)."""
        try:
            with open(raw_path, "wb") as f:
                pending = 0
                while True:
                    item = q.get()
                    if item is None:
                        break
                    f.write(item)
                    pending += len(item)
                    # Vidage régulier (~1 Mo) : en cas de coupure de courant, on ne
                    # perd au pire que la dernière poignée de secondes.
                    if pending >= 1 << 20:
                        f.flush()
                        os.fsync(f.fileno())
                        pending = 0
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            log(f"écriture de la sauvegarde de réunion : {e}")

    def _stop_disk_backup(self):
        """Ferme proprement la sauvegarde en cours et renvoie ses chemins (ou None)."""
        q, t, paths = self._disk_queue, self._disk_thread, self._disk_paths
        self._disk_queue = self._disk_thread = self._disk_paths = None
        if q is None:
            return None
        try:
            q.put(None)
            if t is not None:
                t.join(timeout=10.0)
        except Exception as e:
            log(f"fermeture de la sauvegarde de réunion : {e}")
        return paths

    @staticmethod
    def _discard_disk_backup(paths):
        """Efface une sauvegarde devenue inutile (texte bien enregistré en historique)."""
        if not paths:
            return
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass

    # ------------------------------------------------------------ audio I/O --
    def _make_audio_cb(self, sink, disk_queue, ready=None):
        """Fabrique le callback audio d'UN flux précis.

        Le callback écrit dans la liste `sink` qui lui est propre, et non dans
        self._frames : si un ancien flux n'est pas encore complètement arrêté quand un
        nouvel enregistrement démarre, ses derniers blocs ne peuvent plus polluer le
        nouvel enregistrement.

        `ready` est armé au tout PREMIER bloc reçu. Le retour de `start()` ne prouve
        rien : le matériel peut mettre plusieurs centaines de millisecondes à délivrer
        du son. Ce n'est qu'à ce moment-là qu'il est honnête de dire « parle »."""
        def cb(indata, _frames, _time_info, status):
            if status:
                log(f"audio status: {status}")
            # Copie nécessaire : le tampon est réutilisé par PortAudio.
            buf = indata.copy()
            sink.append(buf)
            if ready is not None and not ready.is_set():
                ready.set()       # simple drapeau : rien de coûteux ici
            if disk_queue is not None:
                try:
                    disk_queue.put_nowait(buf.tobytes())
                except Exception:
                    pass          # jamais d'exception dans un callback temps réel
        return cb

    def _announce_ready(self, ready):
        """Joue le son de départ au premier bloc audio réellement capté.

        Sur un micro Bluetooth on se tait : ouvrir une sortie audio pendant que
        l'entrée est ouverte ferait basculer le casque en profil « mains libres »
        (cf. input_is_bluetooth)."""
        if not ready.wait(timeout=2.0):
            log("aucun bloc audio reçu dans les 2 s : micro muet ou occupé ?")
            return
        if input_is_bluetooth():
            return
        self._sounds.play("start")

    def _start_recording(self, mode):
        """Démarre l'enregistrement. Renvoie True si le micro s'est bien ouvert."""
        with self._lock:
            if self._recording:
                return False
            self._recording = True
            self._record_mode = mode
            frames = []
            self._frames = frames
            self._record_start = time.monotonic()
        self._ui_queue.put(("state", "recording"))
        # On enregistre en int16 (PCM standard, 2 octets/échantillon) : moitié moins
        # de mémoire qu'en float32 pour les longues réunions. La conversion en
        # float32 [-1, 1] attendu par Whisper se fait une seule fois à l'arrêt.
        # On tente 16 kHz directement (CoreAudio convertit proprement) ; en cas
        # d'échec, on enregistre à la fréquence du micro puis on rééchantillonne.
        # Filet de sécurité : seules les RÉUNIONS sont sauvegardées au fil de l'eau
        # (une dictée éclair dure quelques secondes, il n'y a rien à sauver).
        disk_q = None
        if mode == "meeting":
            self._start_disk_backup(16000)
            disk_q = self._disk_queue
        ready = threading.Event()
        if self.config.get("sounds_enabled", True):
            threading.Thread(target=self._announce_ready, args=(ready,), daemon=True).start()
        try:
            self._record_sr = 16000
            self._stream = sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                                          callback=self._make_audio_cb(frames, disk_q, ready))
            self._stream.start()
            log(f"Enregistrement démarré ({mode}, 16000 Hz).")
            return True
        except Exception as e:
            log(f"16 kHz indisponible ({e}) — repli sur la fréquence par défaut du micro.")
            # Si le flux 16 kHz a été OUVERT (constructeur réussi) mais que .start() a
            # échoué, il faut le refermer : sinon le périphérique reste ouvert (micro
            # « chaud ») et on en ouvrirait un second juste après. Fuite de ressource.
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            try:
                info = sd.query_devices(kind="input")
                self._record_sr = int(info["default_samplerate"])
            except Exception:
                self._record_sr = 48000
            # La sauvegarde disque a été ouverte en annonçant 16 kHz : on corrige la
            # fiche, sinon une réunion récupérée serait relue à la mauvaise vitesse.
            if self._disk_paths is not None:
                save_json(self._disk_paths[1], {"sr": int(self._record_sr),
                                                "started": datetime.datetime.now().isoformat(
                                                    timespec="seconds"),
                                                "version": APP_VERSION})
            try:
                self._stream = sd.InputStream(
                    samplerate=self._record_sr, channels=1, dtype="int16",
                    callback=self._make_audio_cb(frames, disk_q, ready))
                self._stream.start()
                log(f"Enregistrement démarré ({mode}, {self._record_sr} Hz, repli).")
                return True
            except Exception as e2:
                log(f"Impossible d'ouvrir le micro : {e2}")
                self._discard_disk_backup(self._stop_disk_backup())
                with self._lock:
                    self._recording = False
                    self._record_mode = None
                self._ui_queue.put(("error", "Impossible d'accéder au micro. Autorise le « Microphone » dans les réglages, puis « Redémarrer VoixFlash »."))
                self._ui_queue.put(("state", "idle"))
                return False

    def _stop_recording(self):
        """Arrête l'enregistrement. Retourne IMMÉDIATEMENT.

        ⚠ Cette méthode est appelée depuis un callback de menu, donc sur le thread
        principal. Tout ce qui peut durer est confié à un thread de fond :
        • stream.stop() attend la fin des callbacks audio et peut bloquer plusieurs
          secondes (voire indéfiniment) si le périphérique a changé en cours de route
          (écouteurs débranchés, veille, micro pris par une autre app) ;
        • la concaténation des blocs d'une réunion d'une heure recopie des centaines
          de mégaoctets.
        Faire ces deux choses ici gelait l'interface — et, comme le verrou était tenu
        pendant ce temps, même les garde-fous ne pouvaient plus rien sauver."""
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            # On entre en phase de transcription : le drapeau interdit qu'un import de
            # fichier (ou une autre transcription) démarre en parallèle. _process_audio le
            # remettra à False dans son `finally`.
            self._transcribing = True
            self._transcribing_meeting = (self._record_mode == "meeting")
            self._transcribe_cancel = False
            mode = self._record_mode
            self._record_mode = None
            self._record_start = None
            stream = self._stream
            self._stream = None
            record_sr = self._record_sr
            # On garde la MÊME liste que le callback : lui continuera d'y ajouter les
            # derniers blocs jusqu'à ce que stream.stop() rende la main, et le thread de
            # fond ne la lira qu'après. Rien n'est perdu. Un futur enregistrement, lui,
            # repartira sur une liste neuve (créée par _start_recording).
            frames = self._frames
            self._frames = []
        self._ui_queue.put(("state", "transcribing"))
        threading.Thread(target=self._finalize_recording,
                         args=(stream, frames, record_sr, mode), daemon=True).start()

    def _cancel_recording(self, reason):
        """Abandonne l'enregistrement en cours SANS transcrire (thread de fond).

        Sert aux appuis involontaires : touche relâchée aussitôt, accord de touches,
        ou Échap. On libère le micro par le MÊME chemin qu'un arrêt normal, sinon
        l'indicateur d'enregistrement de macOS resterait allumé indéfiniment."""
        # Remis à zéro AVANT toute sortie anticipée : si l'ouverture du micro avait
        # échoué, l'état « touche maintenue » resterait sinon coincé à vrai et plus
        # aucune dictée ne démarrerait.
        self._ptt_active = False
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            self._record_mode = None
            self._record_start = None
            stream = self._stream
            self._stream = None
            frames = self._frames
            self._frames = []
        log(f"Dictée {reason}.")

        def _teardown():
            # Quoi qu'il arrive pendant la libération, l'indicateur DOIT repasser au
            # repos : sinon l'icône reste figée sur « enregistrement » et l'app paraît
            # bloquée alors qu'elle ne fait plus rien.
            try:
                try:
                    if stream is not None:
                        stream.stop()
                        stream.close()
                except Exception as e:
                    log(f"fermeture flux (annulation) : {e}")
                self._discard_disk_backup(self._stop_disk_backup())
                frames.clear()
                if self.config.get("sounds_enabled", True):
                    self._sounds.play("error")
            except Exception as e:
                log(f"annulation de la dictée : {e}")
            finally:
                self._ui_queue.put(("state", "idle"))

        threading.Thread(target=_teardown, daemon=True).start()

    def _finalize_recording(self, stream, frames, record_sr, mode):
        """Ferme le flux, assemble l'audio, puis lance la transcription. Thread de fond."""
        try:
            t0 = time.monotonic()
            # Traîne de fin : on laisse le flux tourner un court instant avant de le
            # fermer. Couper à l'instant exact du relâchement tranche le dernier mot,
            # qui est encore en vol dans les tampons de CoreAudio. Le callback continue
            # d'alimenter la MÊME liste, donc ces derniers blocs sont bien récupérés.
            if mode == "flash":
                time.sleep(RELEASE_TAIL_S)
            if stream is not None:
                try:
                    stream.stop()    # attend la fin des callbacks (plus aucun ajout)
                    stream.close()
                except Exception as e:
                    log(f"fermeture flux : {e}")
            backup = self._stop_disk_backup()
            audio = self._frames_to_float32(frames)
            log(f"Enregistrement arrêté ({mode}) : {len(audio) / max(1, record_sr):.1f} s "
                f"d'audio, flux fermé en {time.monotonic() - t0:.1f} s.")
            self._process_audio(audio, record_sr, mode, backup=backup)
        except Exception as e:
            log(f"finalisation de l'enregistrement : {e}")
            self._ui_queue.put(("error", f"Erreur à l'arrêt de l'enregistrement : {e}"))
            self._ui_queue.put(("state", "idle"))
            with self._lock:
                self._transcribing = False
                self._transcribing_meeting = False

    @staticmethod
    def _frames_to_float32(frames):
        """Assemble les blocs int16 en UN tableau float32 normalisé dans [-1, 1].

        Conversion bloc par bloc, chaque bloc étant libéré dès qu'il est recopié.
        Un np.concatenate suivi d'un .astype puis d'une division ferait coexister
        l'int16 complet, sa copie float32 et le résultat de la division : près de
        trois fois la taille finale. Sur une réunion d'une heure (350 Mo d'int16),
        le pic dépassait le gigaoctet et l'app pouvait être tuée par le système."""
        total = sum(len(b) for b in frames)
        if total == 0:
            frames.clear()
            return np.zeros(0, dtype=np.float32)
        audio = np.empty(total, dtype=np.float32)
        pos = 0
        for i, blk in enumerate(frames):
            n = len(blk)
            audio[pos:pos + n] = blk.reshape(-1)   # int16 -> float32 à l'affectation
            pos += n
            frames[i] = None                       # libère l'int16 immédiatement
        frames.clear()
        audio /= 32768.0                           # normalisation sur place
        return audio

    def _resample(self, audio, sr_in, sr_out=16000):
        """Rééchantillonnage simple (interpolation linéaire), par tranches.

        La version directe (deux linspace plus np.interp) travaillait en float64 sur
        la TOTALITÉ du signal : pour une réunion d'une heure à 48 kHz, la seule grille
        d'entrée pesait 1,4 Go, et le pic cumulé dépassait les 3 Go. On découpe donc
        la sortie en tranches, ce qui ramène le surcoût à quelques dizaines de Mo.
        Résultat numériquement identique à l'ancienne formule."""
        if sr_in == sr_out or len(audio) == 0:
            return audio
        n_in = len(audio)
        n_out = int(round(n_in * sr_out / sr_in))
        if n_out <= 0:
            return np.zeros(0, dtype=np.float32)
        out = np.empty(n_out, dtype=np.float32)
        ratio = n_in / n_out
        CHUNK = 1 << 20
        for start in range(0, n_out, CHUNK):
            stop = min(start + CHUNK, n_out)
            pos = np.arange(start, stop, dtype=np.float64) * ratio
            left = np.floor(pos).astype(np.int64)
            frac = pos - left
            np.clip(left, 0, n_in - 1, out=left)
            right = np.minimum(left + 1, n_in - 1)
            out[start:stop] = audio[left] * (1.0 - frac) + audio[right] * frac
        return out

    # ----------------------------------------------------- transcription --
    def _effective_language(self, info=None):
        """Langue à retenir pour le nettoyage du texte.

        Le choix explicite de l'utilisateur prime. En mode « auto », on ne se fie à
        la détection de Whisper que si elle est SÛRE : retirer des hésitations sur
        une langue mal devinée effacerait de vrais mots (« um » est un article en
        portugais). Dans le doute on rend une chaîne vide, et seules les hésitations
        universelles sont retirées."""
        lang = self.config.get("language", "fr")
        if lang != "auto":
            return lang
        try:
            if float(getattr(info, "language_probability", 0) or 0) >= 0.9:
                return str(getattr(info, "language", "") or "")
        except Exception:
            pass
        return ""

    def _process_audio(self, audio, sr, mode, backup=None):
        """Transcrit l'audio d'une dictée ou d'une réunion. Thread de fond.

        `backup` : chemins de la sauvegarde brute de la réunion, effacée seulement
        une fois le texte réellement enregistré dans l'historique."""
        cancelled = False
        try:
            if sr != 16000 and len(audio) > 0:
                audio = self._resample(audio, sr, 16000)
            if len(audio) < 1600:          # moins de 0,1 s : rien à transcrire
                self._discard_disk_backup(backup)
                self._ui_queue.put(("state", "idle"))
                return

            with self._lock:
                model = self.model
            if model is None:
                self._ui_queue.put(("error", "Moteur de transcription indisponible. "
                                             "L'enregistrement est conservé : il te sera "
                                             "proposé au prochain démarrage."))
                self._ui_queue.put(("state", "idle"))
                return

            # Langue : "fr"/"en" forcée, ou "auto" → on passe None à Whisper, qui
            # détecte alors la langue de la dictée (idéal pour alterner FR/EN).
            lang = self.config.get("language", "fr")
            whisper_lang = None if lang == "auto" else lang
            # vad_filter (détection de voix) seulement pour les réunions : il évite
            # de transcrire les longs silences. En dictée éclair on parle exprès,
            # donc on le désactive pour ne jamais perdre un mot.
            # condition_on_previous_text=False : évite les répétitions en boucle.
            t0 = time.monotonic()
            total = len(audio) / 16000.0
            log(f"Transcription démarrée ({mode}, {fmt_duration(total)} d'audio, "
                f"modèle {self.model_name_loaded}).")
            segments, info = model.transcribe(
                audio,
                language=whisper_lang,
                beam_size=int(self.config.get("beam_size", 5)),
                vad_filter=(mode == "meeting"),
                condition_on_previous_text=False,
                initial_prompt=STYLE_PROMPTS.get(whisper_lang),
            )
            # faster-whisper renvoie un GÉNÉRATEUR : le calcul se fait au fur et à
            # mesure qu'on le parcourt. On en profite pour afficher une progression
            # réelle, sauvegarder le texte au fil de l'eau et permettre l'annulation.
            # Sans ça, une réunion d'une heure laissait l'app muette une dizaine de
            # minutes — indiscernable d'un plantage, d'où les fermetures forcées.
            if mode == "meeting":
                seglist, cancelled = self._collect_meeting_segments(segments, total)
            else:
                seglist = list(segments)
            log(f"Transcription terminée ({mode}) : {len(seglist)} passages en "
                f"{time.monotonic() - t0:.1f} s{' (annulée)' if cancelled else ''}.")

            # Séparation des locuteurs (réunions uniquement, si activée et prête). On tient
            # tout l'audio en mémoire ici, donc les identités de locuteurs sont cohérentes
            # sur toute la réunion. Un échec de diarisation NE casse jamais la transcription :
            # format_with_speakers renvoie None et on retombe sur le rendu habituel.
            diar_text = None
            if (mode == "meeting" and self.config.get("diarization_enabled")
                    and diarization_ready()):
                # La diarisation ne doit JAMAIS faire perdre la transcription : toute erreur
                # ici (config, modèle, mémoire) retombe silencieusement sur le texte simple.
                try:
                    diar = diarize(audio, int(self.config.get("diarization_speakers", 0)))
                    diar_text = format_with_speakers(
                        seglist, diar, timestamps=bool(self.config["meeting_timestamps"]))
                except Exception as e:
                    log(f"diarisation ignorée (repli sur texte simple) : {e}")
                    diar_text = None

            if diar_text is not None:
                text = diar_text
            elif mode == "meeting" and self.config["meeting_timestamps"]:
                # L'horodatage est fourni gratuitement par faster-whisper (start de
                # chaque segment) : on l'ajoute seulement si l'option est activée.
                text = "\n".join(f"[{fmt_ts(s.start)}] {s.text.strip()}" for s in seglist).strip()
            else:
                text = " ".join(s.text.strip() for s in seglist).strip()

            # Garde-fou anti-hallucination (silence/bruit) : on n'écrit rien.
            if is_probably_hallucination(text):
                log(f"Transcription écartée (probable hallucination) : {text!r}")
                text = ""

            # Nettoyage local : hésitations, vocabulaire de l'utilisateur, bégaiements.
            # Le vocabulaire est relu à chaque fois : une modification du fichier prend
            # effet immédiatement, sans redémarrer l'app.
            text = postprocess_text(
                text,
                language=self._effective_language(info),
                vocab=load_vocabulary(),
                remove_hesitations=bool(self.config.get("remove_hesitations", True)),
            )

            if not text:
                # Aucun texte reconnu. En dictée éclair on reste silencieux (rien à
                # coller). En réunion, l'utilisateur a cliqué « Démarrer » puis
                # « Arrêter » : il ATTEND un résultat — un retour vide passerait pour
                # une réunion perdue. On l'informe explicitement.
                if mode == "meeting":
                    # On NE supprime PAS l'enregistrement : « aucun texte détecté » peut
                    # aussi venir d'une mauvaise langue ou d'un micro trop bas. L'audio
                    # est conservé et reproposé au démarrage suivant, où l'utilisateur
                    # pourra réessayer (autre qualité, autre langue) ou le supprimer.
                    garde = (" L'enregistrement est conservé : il te sera reproposé au "
                             "prochain démarrage, où tu pourras réessayer avec une autre "
                             "qualité ou une autre langue." if backup else "")
                    self._ui_queue.put(("error", "Réunion terminée, mais aucun texte n'a "
                                                 "été détecté (micro trop faible, trop loin, "
                                                 f"ou silence).{garde}"))
                self._ui_queue.put(("state", "idle"))
                return

            # Écriture en base depuis ce thread de fond : history_add ouvre sa propre
            # connexion SQLite, c'est sûr. On demande ensuite au thread principal de
            # rafraîchir le menu (« history_changed »).
            entry = history_add(mode, text)
            self._ui_queue.put(("history_changed", None))
            # Le texte est en base : la sauvegarde brute et le brouillon partiel n'ont
            # plus d'utilité. C'est le SEUL endroit où on les efface.
            self._discard_disk_backup(backup)
            self._clear_meeting_partial()
            if cancelled:
                self._ui_queue.put(("info", ("Transcription interrompue",
                                             "La partie déjà transcrite a été enregistrée "
                                             "dans l'historique.")))

            if mode == "flash":
                # Dictée éclair : on colle le texte là où est le curseur.
                self._ui_queue.put(("state", "pasting"))
                self._paste_text(text)
                self._ui_queue.put(("state", "idle"))
            else:
                # Réunion : on affiche le texte dans une fenêtre (sans toucher au
                # presse-papiers ; la copie est un choix explicite dans la fenêtre).
                self._ui_queue.put(("state", "idle"))
                self._ui_queue.put(("meeting_result", entry))

        except Exception as e:
            log(f"Erreur de transcription : {e}")
            # La sauvegarde brute n'est PAS effacée ici : c'est justement le cas où
            # elle sert. Elle sera reproposée au prochain démarrage.
            suite = (" L'enregistrement est conservé : il te sera proposé au prochain "
                     "démarrage." if mode == "meeting" and backup else "")
            self._ui_queue.put(("error", f"Erreur de transcription : {e}.{suite}"))
            self._ui_queue.put(("state", "idle"))
        finally:
            # Fin de la phase de transcription, quel que soit le chemin (succès, audio
            # vide, hallucination, erreur) : on libère le drapeau pour autoriser la
            # prochaine dictée/réunion/import.
            with self._lock:
                self._transcribing = False
                self._transcribing_meeting = False
                self._transcribe_cancel = False
            if mode == "meeting":
                self._ui_queue.put(("meeting_title", MEETING_START_TITLE))

    # ------------------------------- progression / annulation d'une réunion --
    def _meeting_partial_path(self):
        """Brouillon de la transcription en cours (filet anti-plantage)."""
        return os.path.join(TRANSCRIPTS_DIR, "reunion_transcription_en_cours.txt")

    def _clear_meeting_partial(self):
        try:
            os.remove(self._meeting_partial_path())
        except OSError:
            pass

    def _collect_meeting_segments(self, segments, total):
        """Parcourt le générateur de passages en affichant la progression, en
        sauvegardant le texte au fil de l'eau et en respectant une demande
        d'annulation. Renvoie (liste des passages, annulée ?)."""
        seglist = []
        partial = self._meeting_partial_path()
        last_pct = -1
        self._ui_queue.put(("meeting_title", MEETING_TRANSCRIBE_TITLE))
        for s in segments:
            seglist.append(s)
            if total > 0:
                pct = min(99, int(s.end / total * 100))
                if pct != last_pct:
                    last_pct = pct
                    self._ui_queue.put(("meeting_progress", pct))
            # Brouillon sur disque toutes les 10 phrases : si l'app est tuée pendant
            # une longue transcription, le travail déjà fait reste lisible.
            if len(seglist) % 10 == 0:
                try:
                    with open(partial, "w", encoding="utf-8") as f:
                        f.write(" ".join(x.text.strip() for x in seglist))
                except Exception as e:
                    log(f"brouillon de transcription : {e}")
            if self._transcribe_cancel:
                log("Transcription de réunion annulée par l'utilisateur.")
                return seglist, True
        return seglist, False

    # ------------------------------------------------- presse-papiers & collage --
    @staticmethod
    def _run(args, timeout=10, **kw):
        """subprocess.run blindé : délai maximal + aucune exception ne remonte. Un
        utilitaire macOS bloqué (serveur du presse-papiers, LaunchServices, launchctl)
        ne doit jamais figer le thread principal de l'app."""
        try:
            return subprocess.run(args, check=False, timeout=timeout, **kw)
        except Exception as e:
            log(f"run {args[:1]} : {e}")
            return None

    def _set_clipboard(self, text):
        """Met du texte UTF-8 dans le presse-papiers (pbcopy + UTF-8 = accents parfaits)."""
        self._run([PBCOPY], input=text.encode("utf-8"), env=CLIP_ENV, timeout=5)

    def _get_clipboard_bytes(self):
        r = self._run([PBPASTE], capture_output=True, env=CLIP_ENV, timeout=5)
        return r.stdout if r is not None else b""

    @staticmethod
    def _pasteboard():
        """Presse-papiers système via pyobjc, ou None (repli pbcopy/pbpaste)."""
        try:
            from AppKit import NSPasteboard
            return NSPasteboard.generalPasteboard()
        except Exception as e:
            log(f"NSPasteboard indisponible : {e}")
            return None

    @staticmethod
    def _pb_snapshot(pb):
        """Copie INDÉPENDANTE du presse-papiers : tous les éléments, tous leurs types.

        Indispensable : une image, un fichier ou du texte enrichi ne survivent pas à
        un aller-retour par pbpaste, qui ne rend que du texte brut. Les données sont
        recopiées (dataWithData_) car celles de l'original deviennent invalides dès
        que le presse-papiers est vidé."""
        try:
            from AppKit import NSData
            snap = []
            for item in (pb.pasteboardItems() or []):
                entry = []
                for t in (item.types() or []):
                    d = item.dataForType_(t)
                    if d is not None:
                        entry.append((t, NSData.dataWithData_(d)))
                if entry:
                    snap.append(entry)
            return snap
        except Exception as e:
            log(f"lecture du presse-papiers : {e}")
            return None

    @staticmethod
    def _pb_write_dictation(pb, text):
        """Écrit la dictée et renvoie le changeCount qui nous appartient (ou None).

        Les types « org.nspasteboard.* » demandent aux gestionnaires de presse-papiers
        (Raycast, Alfred, Maccy, Paste) de NE PAS archiver le contenu : une dictée est
        de passage, elle n'a rien à faire dans un historique tiers."""
        try:
            from AppKit import NSPasteboardItem, NSPasteboardTypeString
            item = NSPasteboardItem.alloc().init()
            item.setString_forType_(text, NSPasteboardTypeString)
            for marker in ("org.nspasteboard.TransientType",
                           "org.nspasteboard.ConcealedType",
                           "org.nspasteboard.AutoGeneratedType"):
                item.setString_forType_("", marker)
            item.setString_forType_(APP_NAME, "org.nspasteboard.source")
            pb.clearContents()
            if not pb.writeObjects_([item]):
                return None
            return int(pb.changeCount())
        except Exception as e:
            log(f"écriture du presse-papiers : {e}")
            return None

    @staticmethod
    def _pb_restore(pb, snap):
        """Réécrit l'instantané pris avant le collage."""
        try:
            from AppKit import NSPasteboardItem
            items = []
            for entry in snap:
                item = NSPasteboardItem.alloc().init()
                for (t, d) in entry:
                    item.setData_forType_(d, t)
                items.append(item)
            pb.clearContents()
            if items:
                pb.writeObjects_(items)
        except Exception as e:
            log(f"restauration du presse-papiers : {e}")

    def _pb_restore_later(self, pb, gen):
        """Restaure le presse-papiers, mais SEULEMENT s'il est encore le nôtre.

        Deux abandons volontaires : une dictée plus récente a pris la main (génération
        différente), ou l'utilisateur a copié quelque chose entre-temps (changeCount
        différent). Dans les deux cas son geste gagne : restaurer à l'aveugle après un
        délai fixe écrase le travail de l'utilisateur, c'est un bug silencieux."""
        with self._pb_lock:
            pending = self._pb_pending
            if pending is None or pending[0] != gen:
                return
            _, snap, ours = pending
            self._pb_pending = None
            if int(pb.changeCount()) != ours:
                return
        self._pb_restore(pb, snap)

    def _paste_text(self, text):
        """Colle le texte au curseur : presse-papiers + Cmd+V simulé (jamais lettre par lettre)."""
        # Sans l'autorisation « Accessibilité », le Cmd+V simulé n'aurait aucun effet
        # (échec silencieux). On prévient l'utilisateur et on évite d'écraser son
        # presse-papiers ; le texte y est tout de même copié pour un collage manuel.
        if not accessibility_trusted():
            self._set_clipboard(text)
            self._ui_queue.put(("error", "Texte copié, mais collage automatique impossible : "
                                         "autorise « Accessibilité » dans les réglages, puis « Redémarrer VoixFlash »."))
            return
        pb = self._pasteboard()
        if pb is None:
            self._paste_text_basic(text)
            return
        restore = bool(self.config.get("restore_clipboard", True))
        with self._pb_lock:
            self._pb_gen += 1
            gen = self._pb_gen
            pending = self._pb_pending
            if restore and pending is not None and int(pb.changeCount()) == pending[2]:
                # Dictée enchaînée : le presse-papiers contient NOTRE texte précédent.
                # On conserve l'instantané d'origine plutôt que de photographier
                # la dictée précédente, sinon elle deviendrait le « contenu à rendre ».
                snap = pending[1]
            else:
                snap = self._pb_snapshot(pb) if restore else None
            self._pb_pending = None
        ours = self._pb_write_dictation(pb, text)
        if ours is None:
            # Écriture refusée : surtout ne pas envoyer un Cmd+V à l'aveugle, il
            # collerait le contenu PRÉCÉDENT du presse-papiers.
            self._ui_queue.put(("error", "Le presse-papiers n'a pas pu être écrit ; texte conservé dans l'historique."))
            return
        if snap is not None:
            with self._pb_lock:
                self._pb_pending = (gen, snap, ours)
        self._send_cmd_v()
        if snap is not None:
            # Assez tard pour que l'application cible ait lu le presse-papiers, assez
            # tôt pour ne pas retenir en otage celui de l'utilisateur.
            threading.Timer(0.6, self._pb_restore_later, args=(pb, gen)).start()

    def _paste_text_basic(self, text):
        """Repli sans pyobjc : presse-papiers texte seul (comportement historique)."""
        old = self._get_clipboard_bytes() if self.config.get("restore_clipboard", True) else None
        self._set_clipboard(text)
        time.sleep(0.12)
        self._send_cmd_v()
        if old is not None and old.strip():
            time.sleep(0.6)
            if self._get_clipboard_bytes() == text.encode("utf-8"):
                self._run([PBCOPY], input=old, env=CLIP_ENV, timeout=5)

    def _send_cmd_v(self):
        """Simule l'appui Cmd+V (nécessite l'autorisation Accessibilité)."""
        try:
            from Quartz import (
                CGEventCreateKeyboardEvent, CGEventPost, CGEventSetFlags,
                CGEventSourceCreate, kCGEventSourceStatePrivate,
                kCGHIDEventTap, kCGEventFlagMaskCommand,
            )
            # Source PRIVÉE, et non l'état système : sinon les modificateurs encore
            # PHYSIQUEMENT enfoncés au moment du collage (typiquement notre propre
            # touche de dictée, qu'on vient à peine de relâcher) se mélangent aux
            # nôtres et produisent un Cmd+Maj+V au lieu d'un Cmd+V.
            src = CGEventSourceCreate(kCGEventSourceStatePrivate)
            # Code de la touche « v » en QWERTY/AZERTY. Une disposition Bépo, Dvorak
            # ou Colemak place une autre lettre ici : limitation connue, documentée.
            V_KEYCODE = 9
            down = CGEventCreateKeyboardEvent(src, V_KEYCODE, True)
            CGEventSetFlags(down, kCGEventFlagMaskCommand)
            up = CGEventCreateKeyboardEvent(src, V_KEYCODE, False)
            CGEventSetFlags(up, kCGEventFlagMaskCommand)
            CGEventPost(kCGHIDEventTap, down)
            time.sleep(0.01)   # certaines apps ratent un appui/relâchement trop serré
            CGEventPost(kCGHIDEventTap, up)
        except Exception as e:
            log(f"Cmd+V : {e}")
            self._ui_queue.put(("error", "Collage impossible : autorise « Accessibilité » dans les réglages."))

    # --------------------------------------------- boucle UI (thread principal) --
    # Messages qui touchent à la STRUCTURE d'un menu (on retire puis on rajoute des
    # items). Reconstruire un NSMenu pendant que l'utilisateur le déroule peut faire
    # planter l'app : ces messages-là attendent le retour au mode de boucle normal.
    _MENU_REBUILD_KINDS = ("history_changed", "diar_installed")

    def _install_timer_common_modes(self):
        """Fait battre le minuteur d'interface DANS TOUS LES MODES de la boucle
        d'événements.

        rumps n'inscrit son NSTimer qu'en NSDefaultRunLoopMode. Conséquence : dès
        qu'un menu est déroulé ou qu'une fenêtre est ouverte, macOS bascule en mode
        « suivi » et le minuteur CESSE de battre — l'indicateur d'état se fige et les
        messages des threads de fond s'empilent sans jamais être appliqués. On
        inscrit donc le même minuteur dans les modes communs."""
        if NSRunLoop is None or NSRunLoopCommonModes is None:
            return
        try:
            NSRunLoop.currentRunLoop().addTimer_forMode_(
                self._timer._nstimer, NSRunLoopCommonModes)
        except Exception as e:
            log(f"minuteur (modes communs) : {e}")

    def _runloop_is_idle(self):
        """True si la boucle d'événements est dans son mode NORMAL, c'est-à-dire
        qu'aucun menu n'est déroulé et qu'aucune fenêtre modale n'est ouverte.
        Renvoie True si l'information est indéterminable (comportement d'avant)."""
        if NSRunLoop is None or NSDefaultRunLoopMode is None:
            return True
        try:
            mode = NSRunLoop.currentRunLoop().currentMode()
        except Exception:
            return True
        return mode is None or str(mode) == str(NSDefaultRunLoopMode)

    def _drain_ui(self, _timer):
        """Appelée par le minuteur sur le thread principal : applique les changements d'UI."""
        try:
            idle = self._runloop_is_idle()
            batch = self._deferred          # ce qui attendait un moment sûr
            self._deferred = []
            while True:
                try:
                    batch.append(self._ui_queue.get_nowait())
                except queue.Empty:
                    break
            for kind, payload in batch:
                if kind in self._MENU_REBUILD_KINDS and not idle:
                    self._deferred.append((kind, payload))
                    continue
                self._apply_ui(kind, payload)
        except Exception as e:
            log(f"drain UI : {e}")

    def _apply_ui(self, kind, payload):
        """Applique UN message d'interface. Thread principal uniquement."""
        try:
            if kind == "state":
                self._state = payload
                self._apply_state_icon(payload)
            elif kind == "history_changed":
                self._refresh_history_menu()
            elif kind == "meeting_result":
                self._present(self._show_transcript, payload)
            elif kind == "meeting_title":
                # Demande du thread de garde-fous : remettre le titre du menu réunion.
                self.meeting_item.title = payload
            elif kind == "import_title":
                # Bascule du libellé de l'item d'import (Importer ↔ Annuler ↔ repos).
                self.import_item.title = payload
            elif kind == "import_progress":
                # Progression d'un import affichée dans le titre du menu (non modal). On
                # GARDE le mot « Annuler » : l'item reste cliquable pour interrompre.
                self.import_item.title = f"Annuler la transcription… ({payload} %)"
            elif kind == "error":
                self._present(self._show_error, payload)
            elif kind == "info":
                title, msg = payload
                self._present(self._show_info, title, msg)
            elif kind == "diar_installed":
                # Fin de l'installation du module de séparation des locuteurs.
                self.diar_item.title = "Séparer les locuteurs (réunions)"
                if payload:
                    self.config["diarization_enabled"] = True
                    save_json(CONFIG_PATH, self.config)
                    self._refresh_diar_menu()
                    self._present(self._show_info, "Séparation des locuteurs activée",
                                  "C'est prêt ! Tes prochaines réunions distingueront "
                                  "« Locuteur 1 », « Locuteur 2 », etc.\n\nAstuce : indique "
                                  "le nombre de personnes dans « Réunions › Locuteurs "
                                  "attendus » si tu le connais — sinon, laisse « Automatique ».")
                else:
                    self._refresh_diar_menu()
                    self._present(self._show_error,
                                  "Le module de séparation des locuteurs n'a pas pu être "
                                  "installé (téléchargement interrompu ou connexion coupée). "
                                  "Réessaie depuis « Réunions › Séparer les locuteurs ».")
            elif kind == "meeting_progress":
                # Progression de la transcription d'une réunion, dans le titre de
                # l'item (non modal). On GARDE le mot « Annuler » : l'item reste
                # cliquable pour interrompre et garder ce qui est déjà transcrit.
                self.meeting_item.title = f"Annuler la transcription… ({payload} %)"
            elif kind == "recover_meeting":
                self._present(self._offer_recovery, payload)
            elif kind == "welcome":
                self._present(self._show_welcome)
        except Exception as e:
            log(f"application UI ({kind}) : {e}")

    def _present(self, func, *args):
        """Affiche une fenêtre modale au tour de boucle SUIVANT.

        Deux raisons, toutes deux importantes :
        • le drain rend la main tout de suite, donc l'indicateur ne se fige pas ;
        • callAfter n'est distribué QUE dans le mode normal de la boucle. Les fenêtres
          s'ouvrent donc forcément l'une après l'autre, jamais imbriquées, et jamais
          pendant qu'un menu est déroulé."""
        if AppHelper is not None:
            try:
                AppHelper.callAfter(func, *args)
                return
            except Exception as e:
                log(f"callAfter : {e}")
        func(*args)

    def _watchdog_loop(self):
        """Boucle de garde-fous, sur un thread dédié (réveil toutes les 2 s). Elle
        survit aux fenêtres modales qui figent le thread principal."""
        while True:
            time.sleep(2.0)
            try:
                self._watchdogs()
            except Exception as e:
                log(f"watchdog loop : {e}")

    def _watchdogs(self):
        """Petites vérifications de sécurité, sans coût notable au repos.
        ⚠ Exécuté hors du thread principal : ne JAMAIS toucher l'UI directement,
        toujours passer par self._ui_queue. _stop_recording / _start_listener sont
        sûrs hors du thread principal (verrou interne, pas d'appel Cocoa d'UI)."""
        # 1) Relancer l'écoute clavier si son thread est mort (sinon plus de dictée).
        #    Bridé à une tentative toutes les 10 s pour éviter toute rafale si une
        #    autorisation manque durablement.
        try:
            if self._listener is not None and not self._listener.is_alive():
                now = time.monotonic()
                if now - self._last_listener_restart > 10.0:
                    self._last_listener_restart = now
                    log("Écoute clavier interrompue : relance automatique.")
                    self._start_listener()
        except Exception:
            pass
        # 1 bis) Réarmement demandé pendant un enregistrement (réveil du Mac) : on
        #        attend que le micro soit libre pour ne rien interrompre.
        try:
            if self._need_rearm and not self._recording and not self._ptt_active:
                self._rearm_listener("réveil différé")
        except Exception:
            pass
        # 2) Arrêter un enregistrement anormalement long (micro oublié, mémoire).
        try:
            if self._recording and self._record_start is not None:
                elapsed = time.monotonic() - self._record_start
                mode = self._record_mode
                if mode == "meeting" and elapsed > MAX_MEETING_SECONDS:
                    self._ui_queue.put(("meeting_title", MEETING_START_TITLE))
                    self._stop_recording()
                    self._ui_queue.put(("error", "Réunion arrêtée automatiquement après 3 h."))
                elif mode == "flash" and elapsed > MAX_FLASH_SECONDS:
                    self._ptt_active = False
                    self._stop_recording()
        except Exception as e:
            log(f"watchdog : {e}")

    @staticmethod
    def _modal_alert(**kwargs):
        """UNIQUE point de passage vers rumps.alert.

        Le passage au premier plan (app_to_front) est indispensable : sans lui,
        l'alerte s'ouvre derrière la fenêtre active et son runModal() bloque le
        thread principal sur un dialogue que l'utilisateur ne voit pas. L'app paraît
        alors gelée alors qu'elle attend simplement un clic.

        Renvoie le bouton cliqué : 1 = ok, 0 = cancel, -1 = other (jamais d'exception)."""
        try:
            app_to_front()
            r = rumps.alert(**kwargs)
        except Exception as e:
            log(f"alerte : {e} — {kwargs.get('title')} : {kwargs.get('message')}")
            return 0
        # Sur macOS actuel, ce type d'alerte renvoie déjà 1 / 0 / -1. Certaines
        # versions renvoient des NSModalResponse (1000, 1001…) numérotés dans l'ordre
        # d'affichage des boutons : on ramène alors à la même convention, pour qu'un
        # « Annuler » ne puisse jamais être pris pour un « Confirmer ».
        if isinstance(r, int) and r >= 1000:
            ordre = [1]
            if kwargs.get("other"):
                ordre.append(-1)
            if kwargs.get("cancel"):
                ordre.append(0)
            idx = r - 1000
            return ordre[idx] if 0 <= idx < len(ordre) else 0
        return r

    def _show_error(self, msg):
        """Affiche une erreur de façon TOUJOURS visible (alerte, marche sans bundle)."""
        self._modal_alert(title=APP_NAME, message=msg, ok="OK")

    def _show_info(self, title, msg):
        """Petite information visible (les notifications macOS ne marchent pas hors bundle)."""
        self._modal_alert(title=title, message=msg, ok="OK")

    def _confirm(self, msg, ok="Confirmer", cancel="Annuler"):
        """Demande une confirmation. Renvoie True si l'utilisateur valide."""
        return self._modal_alert(title=APP_NAME, message=msg, ok=ok, cancel=cancel) == 1

    # ------------------------------------------------------------- actions menu --
    def toggle_meeting(self, sender):
        """Démarre / arrête l'enregistrement long d'une réunion."""
        # Lecture cohérente de l'état partagé (sans garder le verrou pendant les
        # actions, qui le reprennent elles-mêmes).
        with self._lock:
            recording = self._recording
            mode = self._record_mode
            transcribing_meeting = self._transcribing_meeting
        if recording and mode == "flash":
            return  # une dictée éclair est en cours, on ne touche à rien
        if transcribing_meeting and not recording:
            # L'item sert alors de bouton « Annuler » : on interrompt la transcription
            # en gardant ce qui a déjà été reconnu (comme pour un import).
            with self._lock:
                self._transcribe_cancel = True
            sender.title = "Annulation en cours…"
            return
        if not recording:
            if self._transcribing:
                # Un import de fichier est en cours de transcription : on ne lance pas
                # un enregistrement par-dessus.
                self._present(self._show_error, "Une transcription est déjà en cours, réessaie dans un instant.")
                return
            if self.model is None:
                self._present(self._show_error, "Le moteur de transcription se charge encore, réessaie dans un instant.")
                return
            # On ne met le titre « Arrêter » que si le micro s'est réellement ouvert.
            if self._start_recording("meeting"):
                sender.title = MEETING_STOP_TITLE
        else:
            sender.title = MEETING_START_TITLE
            self._stop_recording()

    # --------------------------------------- réunions interrompues (récupération) --
    def _offer_recovery(self, items):
        """Propose de transcrire les réunions retrouvées sur le disque au démarrage.
        Thread principal (appelée via _present)."""
        for raw, meta, sr, dur in items:
            choix = self._modal_alert(
                title="Réunion interrompue retrouvée",
                message=f"Un enregistrement de {fmt_duration(dur)} n'a jamais été "
                        "transcrit (VoixFlash a été fermé ou interrompu pendant la "
                        "réunion).\n\nL'audio est intact. Que veux-tu en faire ?\n\n"
                        "« Plus tard » le garde : il te sera reproposé au prochain "
                        "démarrage.",
                ok="Transcrire maintenant", cancel="Plus tard", other="Supprimer",
            )
            if choix == -1:                          # Supprimer
                # Confirmation obligatoire : « Supprimer » se retrouve juste sous le
                # bouton par défaut, et l'audio effacé ici est irrécupérable.
                if self._confirm(
                        f"Supprimer définitivement cet enregistrement de "
                        f"{fmt_duration(dur)} ? Il n'a jamais été transcrit et ne "
                        "pourra plus l'être.",
                        ok="Supprimer", cancel="Le garder"):
                    self._discard_disk_backup((raw, meta))
                    log(f"Réunion interrompue supprimée : {os.path.basename(raw)}")
                continue
            if choix != 1:                           # Plus tard
                continue
            # ⚠ Jamais d'alerte sous le verrou : elle bloque le thread principal
            # jusqu'au clic, et tous les threads de fond resteraient bloqués derrière.
            with self._lock:
                occupe = self._recording or self._transcribing
                if not occupe:
                    self._transcribing = True
                    self._transcribing_meeting = True
                    self._transcribe_cancel = False
            if occupe:
                self._show_error("Une transcription est déjà en cours. "
                                 "La réunion retrouvée te sera reproposée plus tard.")
                return
            self._ui_queue.put(("state", "transcribing"))
            threading.Thread(target=self._run_recovery, args=(raw, meta, sr),
                             daemon=True).start()
            return          # une seule à la fois : les autres reviendront au démarrage suivant

    def _run_recovery(self, raw, meta, sr):
        """Relit une sauvegarde brute et la transcrit comme une réunion. Thread de fond."""
        try:
            log(f"Reprise de la réunion interrompue : {os.path.basename(raw)}")
            # La proposition arrive au démarrage, souvent AVANT que le moteur soit
            # chargé : on l'attend ici plutôt que de renvoyer l'utilisateur à plus tard.
            attente = 0.0
            while self.model is None and attente < 180.0:
                time.sleep(1.0)
                attente += 1.0
            if self.model is None:
                self._ui_queue.put(("error", "Le moteur de transcription n'a pas pu être "
                                             "chargé. L'enregistrement est conservé : il te "
                                             "sera reproposé au prochain démarrage."))
                self._ui_queue.put(("state", "idle"))
                with self._lock:
                    self._transcribing = False
                    self._transcribing_meeting = False
                return
            pcm = np.fromfile(raw, dtype=np.int16)
            audio = pcm.astype(np.float32) / 32768.0
            del pcm
            self._process_audio(audio, sr, "meeting", backup=(raw, meta))
        except Exception as e:
            log(f"reprise de réunion : {e}")
            self._ui_queue.put(("error", f"Impossible de relire l'enregistrement retrouvé : {e}"))
            self._ui_queue.put(("state", "idle"))
            with self._lock:
                self._transcribing = False
                self._transcribing_meeting = False

    def _abort_recording(self):
        """Coupe le micro SANS transcrire, en gardant la sauvegarde brute sur le disque.
        Utilisé au redémarrage / à la fermeture : la réunion sera reproposée au
        prochain démarrage plutôt que perdue."""
        with self._lock:
            if not self._recording:
                return False
            self._recording = False
            self._record_mode = None
            self._record_start = None
            stream = self._stream
            self._stream = None
            self._frames = []
        try:
            if stream is not None:
                stream.stop()
                stream.close()
        except Exception as e:
            log(f"arrêt du flux (abandon) : {e}")
        paths = self._stop_disk_backup()
        log(f"Enregistrement interrompu et conservé : "
            f"{os.path.basename(paths[0]) if paths else 'aucune sauvegarde'}")
        return True

    # ------------------------------------------------ import d'un fichier audio --
    def _pick_audio_file(self):
        """Ouvre le sélecteur de fichier natif macOS et renvoie le chemin choisi (ou None
        si annulé / indisponible). Appelé depuis un callback de menu, donc sur le thread
        principal — `runModal()` y est légitime (comme rumps.alert)."""
        if NSOpenPanel is None:
            self._show_error("Sélecteur de fichier indisponible sur ce système.")
            return None
        try:
            app_to_front()          # sinon le sélecteur s'ouvre derrière l'app active
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseFiles_(True)
            panel.setCanChooseDirectories_(False)
            panel.setAllowsMultipleSelection_(False)
            panel.setResolvesAliases_(True)
            panel.setTitle_("Choisir un fichier audio ou vidéo à transcrire")
            # Types acceptés (PyAV décode l'audio de tous) : on s'appuie sur les extensions
            # plutôt que sur des UTType (compatibles toutes versions de macOS).
            panel.setAllowedFileTypes_([
                "mp3", "m4a", "aac", "wav", "aif", "aiff", "caf", "flac",
                "ogg", "oga", "opus", "wma", "amr",
                "mp4", "m4v", "mov", "avi", "mkv", "webm",  # vidéos : on prend la piste audio
            ])
            ok = (NSModalResponseOK if NSModalResponseOK is not None else 1)
            if panel.runModal() != ok:
                return None
            urls = panel.URLs()
            if not urls or urls.count() == 0:
                return None
            # .path() renvoie une NSString (sous-classe de str) : on la fige en str Python
            # pur pour qu'elle traverse av.open / os.path sans surprise.
            return str(urls.objectAtIndex_(0).path())
        except Exception as e:
            log(f"_pick_audio_file : {e}")
            self._show_error(f"Impossible d'ouvrir le sélecteur de fichier : {e}")
            return None

    def import_audio_file(self, sender):
        """Callback du menu « Importer un fichier audio… ».

        Deux comportements selon l'état :
        • PENDANT un import (l'item s'intitule « Annuler… ») : on demande l'annulation.
        • AU REPOS : on vérifie les garde-fous (moteur prêt, rien d'autre en cours), on
          fait choisir un fichier, on lit sa durée pour prévenir si c'est long, puis on
          lance la transcription par blocs dans un thread de fond (_run_import)."""
        # --- cas « annulation » : un import de FICHIER est déjà en cours ---
        with self._lock:
            importing = self._importing
            if importing:
                # On pose le drapeau SOUS LE VERROU (cohérence avec les autres drapeaux) ;
                # _run_import s'arrête au prochain bloc en gardant le texte déjà transcrit.
                # (Une transcription de réunion, elle, n'amène pas ce bouton.)
                self._import_cancel = True
        if importing:
            self._ui_queue.put(("import_title", "Annulation en cours…"))
            return

        # --- cas « lancer un import » ---
        if av is None:
            self._show_error("Le décodage audio (PyAV) est indisponible : impossible "
                             "d'importer un fichier sur cette installation.")
            return
        if self.model is None:
            self._show_error("Le moteur de transcription se charge encore, réessaie dans un instant.")
            return
        # ⚠ L'alerte est affichée HORS du verrou : une fenêtre modale bloque le thread
        # principal jusqu'au clic, et le verrou resterait tenu tout ce temps.
        with self._lock:
            occupe = self._recording or self._transcribing
        if occupe:
            self._show_error("Une transcription est déjà en cours, réessaie dans un instant.")
            return

        path = self._pick_audio_file()
        if not path:
            return

        dur, has_audio = audio_stream_info(path)
        if not has_audio:
            self._show_error("Ce fichier ne contient pas de piste audio lisible "
                             "(format non pris en charge, fichier protégé ou corrompu).")
            return

        # Avertissement / confirmation selon la durée (lue sans décoder).
        if dur is not None:
            if dur > IMPORT_MAX_SECONDS:
                if not self._confirm(
                    f"Ce fichier dure {fmt_duration(dur)} — c'est très long.\n"
                    "La transcription peut prendre beaucoup de temps et de mémoire. "
                    "Tu peux l'annuler à tout moment depuis le menu.\nLancer quand même ?",
                    ok="Lancer", cancel="Annuler"):
                    return
            elif dur > IMPORT_WARN_SECONDS:
                est = self._estimate_import_minutes(dur)
                if not self._confirm(
                    f"Ce fichier dure {fmt_duration(dur)}.\n"
                    f"Transcription estimée à ~{est} (selon la qualité choisie). "
                    "Elle tourne en arrière-plan ; tu peux l'annuler depuis le menu.\n"
                    "Lancer ?", ok="Lancer", cancel="Annuler"):
                    return

        # Réservation de l'état et lancement du thread de fond (alerte hors verrou).
        with self._lock:
            occupe = self._recording or self._transcribing
            if not occupe:
                self._transcribing = True
                self._importing = True
                self._import_cancel = False
        if occupe:
            self._show_error("Une transcription est déjà en cours, réessaie dans un instant.")
            return
        self._ui_queue.put(("state", "transcribing"))
        self._ui_queue.put(("import_title", IMPORT_CANCEL_TITLE))
        threading.Thread(target=self._run_import, args=(path, dur), daemon=True).start()

    def _estimate_import_minutes(self, duration_seconds):
        """Estimation lisible du temps de transcription (≈ durée × facteur du modèle)."""
        factor = IMPORT_RT_FACTOR.get(self.config.get("model", "small"), 0.25)
        secs = max(1, int(duration_seconds * factor))
        if secs < 90:
            return f"{secs} s"
        return f"{round(secs / 60)} min"

    def _run_import(self, path, total_dur):
        """Transcrit un fichier audio EN BLOCS, dans un thread de fond. Réutilise la même
        logique de rendu qu'une réunion (horodatage, anti-hallucination, historique, fenêtre
        de résultat), mais en streaming pour borner la mémoire et permettre progression +
        annulation + sauvegarde partielle. La langue est détectée sur le 1er bloc puis FIGÉE
        pour tous les suivants (cohérence sur tout le fichier)."""
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        partial_path = os.path.join(TRANSCRIPTS_DIR, f"import_partiel_{stamp}.txt")
        pieces = []                         # textes des blocs déjà transcrits
        forced_lang = None                  # langue figée après le 1er bloc
        timestamps = bool(self.config.get("meeting_timestamps"))
        beam = int(self.config.get("beam_size", 5))
        vocab = load_vocabulary()           # lu une fois : un import peut durer longtemps
        sep = "\n" if timestamps else " "   # défini AVANT la boucle : réutilisé même en cas
        cancelled = False                   # d'exception (sauvetage des blocs déjà faits)
        try:
            with self._lock:
                model = self.model
            if model is None:
                self._ui_queue.put(("error", "Moteur de transcription indisponible."))
                return

            for audio, start_sec in iter_audio_chunks(path, cancel_check=lambda: self._import_cancel):
                if self._import_cancel:
                    cancelled = True
                    break
                if len(audio) < 1600:       # bloc < 0,1 s : rien d'exploitable
                    continue
                # 1er bloc en détection auto ; on mémorise la langue et on la force ensuite.
                segments, info = model.transcribe(
                    audio,
                    language=forced_lang,   # None au 1er bloc → auto
                    beam_size=beam,
                    vad_filter=True,
                    condition_on_previous_text=False,
                    initial_prompt=STYLE_PROMPTS.get(forced_lang),
                )
                seglist = list(segments)
                if forced_lang is None and getattr(info, "language", None):
                    forced_lang = info.language

                if timestamps:
                    # Horodatage réaligné sur la position du bloc dans le fichier complet.
                    block = "\n".join(
                        f"[{fmt_ts(s.start + start_sec)}] {s.text.strip()}"
                        for s in seglist).strip()
                else:
                    block = " ".join(s.text.strip() for s in seglist).strip()

                if is_probably_hallucination(block):
                    block = ""              # bloc parasite (silence) : ignoré, pas tout le texte
                if block:
                    block = postprocess_text(
                        block, language=forced_lang or "",
                        vocab=vocab,
                        remove_hesitations=bool(self.config.get("remove_hesitations", True)))
                if block:
                    pieces.append(block)
                    # Sauvegarde partielle : protège le travail déjà fait en cas de
                    # fermeture/plantage pendant un import très long.
                    try:
                        with open(partial_path, "w", encoding="utf-8") as f:
                            f.write(sep.join(pieces))
                    except Exception as e:
                        log(f"sauvegarde partielle import : {e}")

                # Progression (si la durée totale est connue) + pause pour ménager le CPU.
                if total_dur and total_dur > 0:
                    pct = min(99, int((start_sec + len(audio) / 16000) / total_dur * 100))
                    self._ui_queue.put(("import_progress", pct))
                time.sleep(IMPORT_CHUNK_PAUSE)

            text = sep.join(pieces).strip()

            if not text:
                if cancelled:
                    self._ui_queue.put(("info", ("Import annulé",
                                                 "Aucun texte n'avait encore été transcrit.")))
                else:
                    self._ui_queue.put(("error", "Aucun texte n'a été détecté dans ce fichier "
                                                 "(silence, musique seule, ou parole inaudible)."))
                return

            entry = history_add("meeting", text)
            self._ui_queue.put(("history_changed", None))
            if cancelled:
                self._ui_queue.put(("info", ("Import annulé",
                                             "La partie déjà transcrite a été enregistrée "
                                             "dans l'historique.")))
            self._ui_queue.put(("meeting_result", entry))
            # Le texte est maintenant en base (historique) : la sauvegarde partielle n'a plus
            # d'utilité, qu'on soit allé au bout ou qu'on ait annulé. On ne la garde QUE si une
            # exception nous empêche d'arriver ici (filet anti-crash, cf. bloc except).
            try:
                os.remove(partial_path)
            except OSError:
                pass

        except Exception as e:
            log(f"Erreur d'import : {e}")
            # Sauvetage : si des blocs ont déjà été transcrits avant l'erreur (ex. fichier
            # corrompu en cours de route), on les enregistre au lieu de les perdre.
            salvaged = sep.join(pieces).strip()
            if salvaged:
                try:
                    entry = history_add("meeting", salvaged)
                    self._ui_queue.put(("history_changed", None))
                    self._ui_queue.put(("meeting_result", entry))
                    self._ui_queue.put(("error", f"Lecture interrompue ({e}). La partie déjà "
                                                 "transcrite a été enregistrée dans l'historique."))
                    # Le texte est sauvé en base : le fichier partiel devient redondant.
                    try:
                        os.remove(partial_path)
                    except OSError:
                        pass
                except Exception as e2:
                    log(f"sauvetage import : {e2}")
                    self._ui_queue.put(("error", f"Erreur pendant l'import : {e}"))
            else:
                self._ui_queue.put(("error", f"Erreur pendant l'import : {e}"))
        finally:
            with self._lock:
                self._transcribing = False
                self._importing = False
                self._import_cancel = False
            self._ui_queue.put(("import_title", IMPORT_IDLE_TITLE))
            self._ui_queue.put(("state", "idle"))

    def toggle_timestamps(self, sender):
        self.config["meeting_timestamps"] = not self.config["meeting_timestamps"]
        sender.state = self.config["meeting_timestamps"]
        save_json(CONFIG_PATH, self.config)

    def toggle_restore(self, sender):
        self.config["restore_clipboard"] = not self.config["restore_clipboard"]
        sender.state = self.config["restore_clipboard"]
        save_json(CONFIG_PATH, self.config)

    # ------------------------------------------------ vocabulaire (menu « Texte dicté ») --
    def toggle_hesitations(self, sender):
        self.config["remove_hesitations"] = not self.config.get("remove_hesitations", True)
        sender.state = self.config["remove_hesitations"]
        save_json(CONFIG_PATH, self.config)

    def toggle_sounds(self, sender):
        self.config["sounds_enabled"] = not self.config.get("sounds_enabled", True)
        sender.state = self.config["sounds_enabled"]
        save_json(CONFIG_PATH, self.config)
        if self.config["sounds_enabled"]:
            self._sounds.play("start")   # aperçu immédiat du son choisi

    def _vocab_prompt(self, title, message, placeholder=""):
        """Petite fenêtre de saisie. Renvoie le texte saisi, ou None si annulé."""
        try:
            app_to_front()
            win = rumps.Window(title=title, message=message, ok="Ajouter",
                               cancel="Annuler", default_text=placeholder,
                               dimensions=(300, 22))
            resp = win.run()
        except Exception as e:
            log(f"saisie vocabulaire : {e}")
            return None
        if resp.clicked != 1:
            return None
        value = (resp.text or "").strip()
        return value or None

    @staticmethod
    def _vocab_save(vocab):
        save_json(VOCAB_PATH, {"mots": vocab.get("mots", []),
                               "corrections": vocab.get("corrections", {})})

    def vocab_add_word(self, _sender):
        """Ajoute un mot dont l'orthographe doit être respectée (nom propre, jargon).

        Les variantes proches produites par Whisper seront ramenées sur cette
        orthographe, y compris quand il découpe le mot en deux ou trois morceaux."""
        word = self._vocab_prompt(
            "Ajouter un mot au vocabulaire",
            "Écris le mot exactement comme tu veux le voir apparaître (nom propre, "
            "marque, terme métier).\n\nExemple : VoixFlash, Kubernetes, Grob.\n\n"
            "Les variantes approchantes seront corrigées automatiquement.")
        if not word:
            return
        vocab = load_vocabulary()
        if word in vocab["mots"]:
            self._show_info("Déjà présent", f"« {word} » est déjà dans le vocabulaire.")
            return
        vocab["mots"].append(word)
        self._vocab_save(vocab)
        self._show_info("Vocabulaire mis à jour",
                        f"« {word} » sera désormais respecté dans les transcriptions.")

    def vocab_add_correction(self, _sender):
        """Ajoute un remplacement exact : ce que Whisper écrit → ce qu'il faut écrire."""
        wrong = self._vocab_prompt(
            "Corriger une faute récurrente (1/2)",
            "Écris le texte tel que VoixFlash le transcrit AUJOURD'HUI, "
            "c'est-à-dire la version fautive.\n\nExemple : aye pee aye")
        if not wrong:
            return
        right = self._vocab_prompt(
            "Corriger une faute récurrente (2/2)",
            f"Par quoi remplacer « {wrong} » ?\n\nExemple : API\n\n"
            "Tu peux aussi t'en servir comme raccourci de saisie : une phrase "
            "courte qui se transforme en un texte plus long.")
        if right is None:
            return
        vocab = load_vocabulary()
        vocab["corrections"][wrong] = right
        self._vocab_save(vocab)
        self._show_info("Correction enregistrée",
                        f"« {wrong} » deviendra « {right} ».")

    def vocab_open_file(self, _sender):
        """Ouvre vocabulaire.json pour une édition en masse."""
        if not os.path.exists(VOCAB_PATH):
            self._vocab_save(load_vocabulary())
        self._run(["/usr/bin/open", "-t", VOCAB_PATH], timeout=10)

    # ---------------------------------------------- séparation des locuteurs (menu) --
    def _refresh_diar_menu(self):
        """Coche l'état de la diarisation et (re)construit le sous-menu « Locuteurs attendus »."""
        self.diar_item.state = bool(self.config.get("diarization_enabled"))
        self._safe_clear(self.diar_speakers_menu)
        current = int(self.config.get("diarization_speakers", 0))
        for label, val in DIAR_SPEAKER_CHOICES:
            item = rumps.MenuItem(label, callback=self._make_diar_speakers_cb(val))
            item.state = (current == val)
            self.diar_speakers_menu.add(item)

    def _make_diar_speakers_cb(self, val):
        def cb(_sender):
            self.config["diarization_speakers"] = val
            save_json(CONFIG_PATH, self.config)
            self._refresh_diar_menu()
        return cb

    def toggle_diarization(self, _sender):
        """Active / désactive la séparation des locuteurs. À la 1re activation, propose
        d'installer le petit module nécessaire (sherpa-onnx + modèles ONNX depuis GitHub) :
        aucun compte, aucune configuration, hors-ligne ensuite."""
        # Déjà activée → simple désactivation.
        if self.config.get("diarization_enabled"):
            self.config["diarization_enabled"] = False
            save_json(CONFIG_PATH, self.config)
            self._refresh_diar_menu()
            return
        # Installation déjà en cours → on ignore un second clic.
        if self._diar_installing:
            self._show_info("Installation en cours",
                            "Le module de séparation des locuteurs s'installe. Un message "
                            "s'affichera dès que ce sera prêt.")
            return
        # Module déjà présent → activation immédiate.
        if diarization_ready():
            self.config["diarization_enabled"] = True
            save_json(CONFIG_PATH, self.config)
            self._refresh_diar_menu()
            self._show_info(
                "Séparation des locuteurs activée",
                "Tes prochaines réunions distingueront « Locuteur 1 », « Locuteur 2 », etc.\n\n"
                "Astuce : indique le nombre de personnes dans « Réunions › Locuteurs "
                "attendus » seulement si tu en es SÛR — un nombre trop grand découpe une "
                "vraie voix en plusieurs. Dans le doute, laisse « Automatique ».")
            return
        # Sinon : proposer le téléchargement (une seule fois).
        if not self._confirm(
                "La séparation des locuteurs indique « qui parle » dans tes réunions "
                "(« Locuteur 1 : … », « Locuteur 2 : … »).\n\n"
                "Pour l'activer, VoixFlash télécharge un petit module (~50 Mo) une seule "
                "fois. Tout reste sur ton Mac : aucun compte, rien à configurer, et ça "
                "fonctionne ensuite hors-ligne.\n\n"
                "Note : la séparation est fiable sur des voix distinctes ; elle se dégrade "
                "quand plusieurs personnes parlent en même temps.\n\n"
                "Lancer le téléchargement maintenant ?",
                ok="Télécharger et activer", cancel="Plus tard"):
            return
        self._diar_installing = True
        self.diar_item.title = "Installation de la séparation des locuteurs…"
        threading.Thread(target=self._install_diarization, daemon=True).start()

    def _install_diarization(self):
        """Thread de fond : installe sherpa-onnx (via uv, comme le reste de l'app) puis
        télécharge les 2 modèles ONNX depuis GitHub. Ne touche jamais l'UI directement :
        tout retour passe par self._ui_queue (« diar_installed »)."""
        ok = False
        try:
            # 1) sherpa-onnx dans le venv de l'app, s'il n'est pas déjà importable.
            if _load_sherpa() is None:
                self._ui_queue.put(("info", ("Téléchargement du module",
                                             "Installation du moteur de séparation… "
                                             "(quelques minutes selon ta connexion).")))
                if not self._pip_install("sherpa-onnx"):
                    raise RuntimeError("installation de sherpa-onnx impossible")
                # Réinitialise le cache d'import pour retenter après installation.
                global _sherpa, _sherpa_tried
                _sherpa = None
                _sherpa_tried = False
                if _load_sherpa() is None:
                    raise RuntimeError("sherpa-onnx installé mais non importable")
            # 2) Modèles ONNX (idempotent : on ne retélécharge pas ce qui est déjà là).
            os.makedirs(DIAR_DIR, exist_ok=True)
            if not os.path.exists(DIAR_SEG_PATH):
                self._download_seg_model()
            if not os.path.exists(DIAR_EMB_PATH):
                self._download_file(DIAR_EMB_URL, DIAR_EMB_PATH)
            ok = diarization_ready()
        except Exception as e:
            log(f"installation diarisation : {e}")
            ok = False
        finally:
            self._diar_installing = False
            self._ui_queue.put(("diar_installed", ok))

    @staticmethod
    def _find_uv():
        """Localise l'outil `uv` (celui utilisé par l'installateur). Le venv de l'app est
        créé sans pip → uv est la voie fiable pour installer un paquet à chaud."""
        import shutil
        for c in (shutil.which("uv"),
                  os.path.expanduser("~/.local/bin/uv"),
                  os.path.expanduser("~/.cargo/bin/uv")):
            if c and os.path.exists(c):
                return c
        return None

    def _pip_install(self, pkg):
        """Installe un paquet dans le venv de l'app. uv d'abord (venv sans pip), puis
        repli sur `python -m pip` (avec amorçage ensurepip si besoin)."""
        py = sys.executable
        uv = self._find_uv()
        attempts = []
        if uv:
            attempts.append([uv, "pip", "install", "--python", py, pkg])
        attempts.append([py, "-m", "pip", "install", pkg])
        for cmd in attempts:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                if r.returncode == 0:
                    return True
                log(f"pip install {pkg} ({os.path.basename(cmd[0])}) rc={r.returncode} : "
                    f"{(r.stderr or '')[-300:]}")
            except Exception as e:
                log(f"pip install {pkg} ({os.path.basename(cmd[0])}) : {e}")
        # Dernier recours : amorcer pip dans le venv puis réessayer une fois.
        try:
            subprocess.run([py, "-m", "ensurepip", "--upgrade"],
                           capture_output=True, text=True, timeout=180)
            r = subprocess.run([py, "-m", "pip", "install", pkg],
                               capture_output=True, text=True, timeout=900)
            return r.returncode == 0
        except Exception as e:
            log(f"ensurepip+pip {pkg} : {e}")
            return False

    @staticmethod
    def _download_file(url, dest):
        """Télécharge une URL vers `dest` de façon atomique (fichier .part puis renommage :
        pas de fichier à moitié écrit si l'opération est interrompue)."""
        import urllib.request
        tmp = dest + ".part"
        # User-Agent explicite : certains CDN/miroirs refusent « Python-urllib » par défaut.
        req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, dest)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def _download_seg_model(self):
        """Télécharge l'archive de segmentation (.tar.bz2) et en extrait model.onnx vers
        DIAR_SEG_PATH (écriture atomique)."""
        import urllib.request
        import tarfile
        tmp = DIAR_SEG_PATH + ".tar.bz2"
        req = urllib.request.Request(DIAR_SEG_URL, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            with tarfile.open(tmp, "r:bz2") as tar:
                member = next((m for m in tar.getmembers()
                               if m.name.endswith("model.onnx")), None)
                if member is None:
                    raise RuntimeError("model.onnx introuvable dans l'archive de segmentation")
                src = tar.extractfile(member)
                with open(DIAR_SEG_PATH + ".part", "wb") as out:
                    out.write(src.read())
            os.replace(DIAR_SEG_PATH + ".part", DIAR_SEG_PATH)
        finally:
            for p in (tmp, DIAR_SEG_PATH + ".part"):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass

    def export_last_meeting(self, _sender):
        """Exporte la dernière réunion en fichier .txt daté (révélé dans le Finder)."""
        entry = history_last_meeting()
        if not entry or not (entry.get("text") or "").strip():
            self._show_info("VoixFlash", "Aucune réunion à exporter pour l'instant.")
            return
        self._export_entry_txt(entry, prefix="reunion")

    def _export_entry_txt(self, entry, prefix="transcription"):
        """Écrit le texte d'une entrée dans un .txt daté et le révèle dans le Finder."""
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        path = os.path.join(TRANSCRIPTS_DIR, f"{prefix}_{stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(entry.get("text", ""))
            self._run([OPEN, "-R", path])   # révèle le fichier dans le Finder
            self._show_info("Exporté", f"Fichier créé :\n{path}")
        except Exception as e:
            log(f"export txt : {e}")
            self._show_info("VoixFlash", f"Échec de l'export : {e}")

    def export_all_history(self, _sender):
        """Exporte tout l'historique dans un .txt lisible (copie ponctuelle ; l'historique
        de référence reste la base SQLite). Fichier daté : on n'écrase pas l'export précédent."""
        entries = history_all()
        if not entries:
            self._show_info("VoixFlash", "L'historique est vide.")
            return
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        path = os.path.join(TRANSCRIPTS_DIR, f"historique_{stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                for e in entries:
                    tag = "RÉUNION" if e.get("mode") == "meeting" else "DICTÉE"
                    f.write(f"--- {e.get('ts', '')}  [{tag}] ---\n{e.get('text', '')}\n\n")
            self._run([OPEN, path])
            self._show_info("Exporté", f"Historique exporté ({len(entries)} entrées) :\n{path}")
        except Exception as e:
            log(f"export historique : {e}")
            self._show_info("VoixFlash", f"Échec de l'export : {e}")

    def clear_history(self, _sender):
        """Vide tout l'historique (après confirmation)."""
        if self._confirm("Vider TOUT l'historique des transcriptions ?\n"
                         "Cette action est irréversible.", ok="Tout vider"):
            history_clear()
            self._refresh_history_menu()

    def _show_transcript(self, entry):
        """Fenêtre d'une transcription (réunion ou dictée). Choix de conception :

        • On NE touche PAS au presse-papiers à l'ouverture (plus d'écrasement subi) :
          la copie est un geste explicite via le bouton « Copier ».
        • Le texte est MODIFIABLE. « Copier » copie la version affichée (modifs comprises).
        • « Enregistrer les modifications » crée une NOUVELLE entrée d'historique si le
          texte a réellement changé (sinon on le signale).
        • « Supprimer » retire l'entrée de l'historique.

        Limite assumée : rumps/NSAlert est modal — chaque bouton ferme la fenêtre. On ne
        peut donc pas griser « Enregistrer » en direct ; on vérifie après coup s'il y a eu
        une modification. C'est volontairement simple et robuste (pas de fenêtre Cocoa
        sur-mesure fragile pour un utilitaire de barre des menus)."""
        original = entry.get("text", "") or ""
        mode = entry.get("mode", "flash")
        entry_id = entry.get("id")
        kind = "réunion" if mode == "meeting" else "dictée"
        ts = entry.get("ts", "")
        # Texte long : le champ de saisie de rumps est un NSTextField simple, sans
        # défilement. Y charger une réunion entière fige le thread principal pendant
        # la mise en page, et le texte reste de toute façon illisible. On passe donc
        # par un vrai fichier ouvert dans TextEdit.
        if len(original) > LONG_TEXT_CHARS:
            self._show_long_transcript(entry, original, kind, ts)
            return
        try:
            app_to_front()
            win = rumps.Window(
                title=f"Transcription · {kind}",
                message=f"{ts}\n\nModifie le texte si besoin, puis choisis une action.",
                default_text=original,
                ok="Fermer",                                  # bouton 1 (à droite)
                dimensions=(480, 360),
            )
            win.add_button("Copier")                          # bouton 2
            win.add_button("Enregistrer les modifications")   # bouton 3
            if entry_id is not None:
                win.add_button("Supprimer")                   # bouton 4
            resp = win.run()
            current = resp.text if resp.text is not None else original

            if resp.clicked == 2:            # Copier (prend en compte les modifications)
                self._set_clipboard(current)
                self._show_info("Copié", "Le texte a été copié dans le presse-papiers.")
            elif resp.clicked == 3:          # Enregistrer les modifications
                if current.strip() and current != original:
                    history_add(mode, current)
                    self._ui_queue.put(("history_changed", None))
                    self._show_info("Modifications enregistrées",
                                    "Une nouvelle entrée a été ajoutée à l'historique.")
                else:
                    self._show_info("Aucune modification",
                                    "Le texte n'a pas changé : rien à enregistrer.")
            elif resp.clicked == 4:          # Supprimer
                if entry_id is not None and self._confirm(
                        "Supprimer définitivement cette entrée de l'historique ?",
                        ok="Supprimer"):
                    history_delete(entry_id)
                    self._ui_queue.put(("history_changed", None))
        except Exception as e:
            log(f"fenêtre transcription : {e}")

    def _show_long_transcript(self, entry, text, kind, ts):
        """Longue transcription : on l'écrit dans un .txt daté et on propose de
        l'ouvrir dans TextEdit (défilement, recherche, modification, impression) —
        tout ce qu'une fenêtre d'alerte ne sait pas faire."""
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = "reunion" if entry.get("mode") == "meeting" else "dictee"
        path = os.path.join(TRANSCRIPTS_DIR, f"{prefix}_{stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            log(f"écriture de la transcription longue : {e}")
            self._show_error(f"Le texte est dans l'historique, mais le fichier n'a pas "
                             f"pu être écrit : {e}")
            return
        mots = len(text.split())
        choix = self._modal_alert(
            title=f"Transcription · {kind}",
            message=f"{ts}\n\nLe texte fait {mots} mots : il est enregistré dans "
                    f"l'historique et dans un fichier.\n\n{path}",
            ok="Ouvrir le texte", cancel="Fermer", other="Copier",
        )
        if choix == 1:
            self._run([OPEN, "-e", path])       # TextEdit
        elif choix == -1:
            self._set_clipboard(text)
            self._show_info("Copié", "Le texte a été copié dans le presse-papiers.")

    # ------------------------------------------------------ aide & autorisations --
    def show_guide(self, _sender):
        """Mode d'emploi complet : rassemble toutes les règles utiles (y compris les
        comportements implicites), dans une fenêtre déroulante. Le texte s'adapte aux
        réglages actuels (touche, presse-papiers, modèle, langue, horodatage)."""
        hk = self._current_hotkey_label()
        restore_on = bool(self.config.get("restore_clipboard", True))
        restore_state = "activé" if restore_on else "désactivé"
        model_labels = {val: label for label, val in MODEL_CHOICES}
        model = model_labels.get(self.config.get("model", "small"), self.config.get("model", "small"))
        lang = {"fr": "Français", "en": "Anglais", "auto": "Automatique"}.get(
            self.config.get("language", "fr"), "Français")
        ts_state = "activé" if self.config.get("meeting_timestamps") else "désactivé"
        hesit_state = "activé" if self.config.get("remove_hesitations", True) else "désactivé"
        sound_state = "activé" if self.config.get("sounds_enabled", True) else "désactivé"

        guide = (
            f"VOIXFLASH {APP_VERSION} — MODE D'EMPLOI COMPLET\n"
            "\n"
            "━━━ 1. LES TROIS FAÇONS DE TRANSCRIRE ━━━\n"
            "\n"
            "• DICTÉE ÉCLAIR (partout)\n"
            "  Place ton curseur dans n'importe quel champ de texte.\n"
            f"  Maintiens la touche « {hk} », parle, puis RELÂCHE.\n"
            "  Le texte s'écrit tout seul à l'endroit du curseur.\n"
            "  (Maintien = on parle ; relâché = ça écrit. Une pression très brève\n"
            "  ne dicte rien.)\n"
            "  Un petit son confirme que le micro écoute : attends-le pour parler.\n"
            "  Un autre son marque la fin de la capture.\n"
            "  ÉCHAP pendant que tu parles annule la dictée : rien n'est écrit.\n"
            "  L'enregistrement continue un court instant après le relâchement, pour\n"
            "  ne pas couper ton dernier mot.\n"
            "\n"
            "• RÉUNION (enregistrement long)\n"
            "  Menu › « Démarrer une réunion ». Parle aussi longtemps que tu veux.\n"
            "  Menu › « Arrêter la réunion » : le texte s'affiche dans une fenêtre\n"
            "  DANS l'application — il n'est PAS collé ailleurs.\n"
            "  La transcription affiche sa progression dans le menu et peut être\n"
            "  interrompue : ce qui est déjà reconnu est gardé.\n"
            "  Une réunion de plus de 4 000 caractères s'ouvre dans TextEdit plutôt\n"
            "  que dans une fenêtre (défilement, recherche, impression).\n"
            "\n"
            "• RIEN N'EST PERDU\n"
            "  Pendant une réunion, l'audio est écrit sur le disque en continu. Si\n"
            "  VoixFlash est fermé de force, plante, ou que le Mac s'éteint, il te\n"
            "  proposera de transcrire l'enregistrement au démarrage suivant.\n"
            "  Idem si tu choisis « Quitter » ou « Redémarrer » pendant une réunion.\n"
            "\n"
            "• IMPORTER UN FICHIER AUDIO (menu › Réunions › « Importer un fichier\n"
            "  audio… »)\n"
            "  Choisis un fichier audio (mp3, m4a, wav, flac, ogg, aiff…) OU une vidéo\n"
            "  (mp4, mov… : seule la piste audio est lue) : VoixFlash le transcrit\n"
            "  comme une réunion (résultat dans une fenêtre + ajouté à l'historique).\n"
            "  • La langue est détectée AUTOMATIQUEMENT (peu importe le réglage Langue).\n"
            "  • Ça tourne en arrière-plan, sans bloquer le Mac ; la progression\n"
            "    s'affiche dans le menu (« Transcription du fichier… NN % »).\n"
            "  • Tu peux ANNULER à tout moment (le même item devient « Annuler la\n"
            "    transcription en cours ») : le texte déjà transcrit est conservé.\n"
            "  • Un fichier long se découpe tout seul en blocs : la mémoire reste\n"
            "    stable même sur 2 h+ d'audio.\n"
            "\n"
            "━━━ 2. CE QUI ARRIVE À TON PRESSE-PAPIERS (à bien comprendre) ━━━\n"
            "\n"
            "La dictée éclair se sert du presse-papiers pour coller (Cmd+V).\n"
            "Comportement selon le réglage « Restaurer le presse-papiers après une\n"
            f"dictée » (actuellement : {restore_state} — activé par défaut) :\n"
            "\n"
            "• Réglage ACTIVÉ (par défaut) :\n"
            "   – presse-papiers VIDE  → il contient ensuite ta dictée ;\n"
            "   – presse-papiers avec du TEXTE → ce texte est REMIS en place juste\n"
            "     après le collage (rien n'est perdu) ;\n"
            "   – presse-papiers avec une IMAGE ou un FICHIER → seul le TEXTE est\n"
            "     protégé : une image/un fichier copié, lui, est remplacé par la dictée.\n"
            "\n"
            "• Réglage DÉSACTIVÉ :\n"
            "   – ta dictée reste toujours dans le presse-papiers (l'ancien contenu\n"
            "     est remplacé à chaque fois).\n"
            "\n"
            "EN MODE RÉUNION, c'est DIFFÉRENT : le presse-papiers n'est JAMAIS touché\n"
            "tout seul. La fenêtre de résultat a un bouton « Copier » que tu cliques\n"
            "toi-même si tu veux copier le texte.\n"
            "\n"
            "━━━ 3. LIMITES & GARDE-FOUS (pour éviter les mauvaises surprises) ━━━\n"
            "\n"
            "• Une RÉUNION s'arrête TOUTE SEULE après 3 HEURES (sécurité : micro oublié\n"
            "  et mémoire). Au-delà, relance une réunion.\n"
            "• Une dictée éclair dont la touche reste enfoncée plus de 2 MINUTES\n"
            "  s'arrête aussi automatiquement.\n"
            "• SILENCE / BRUIT : si rien d'audible n'est dit, RIEN n'est écrit. Un\n"
            "  filtre écarte aussi les phrases parasites que le moteur invente parfois\n"
            "  sur du silence (ex. « Sous-titres réalisés par… ») : non collées.\n"
            "• Au tout premier usage après le démarrage, le premier mot peut tarder\n"
            "  d'une seconde, le temps que le moteur finisse de se charger.\n"
            "• IMPORT D'UN FICHIER : la transcription prend du temps (tout se fait sur le\n"
            "  processeur, sans carte graphique). Compte grossièrement, selon la qualité\n"
            "  choisie : « small » ≈ 1 h d'audio en ~15 min ; « medium » est plus lent.\n"
            "  Un fichier de 2 h passe sans souci (découpage automatique). Au-delà de\n"
            "  30 min, un message annonce une estimation avant de lancer.\n"
            "• L'import ne SÉPARE PAS les locuteurs (c'est un texte continu). La séparation\n"
            "  « qui parle » n'existe que pour les RÉUNIONS enregistrées en direct (voir la\n"
            "  section ci-dessous). Les fichiers protégés (DRM, Apple Music) sont refusés.\n"
            "\n"
            "• SÉPARER LES LOCUTEURS (réunions) : « Réunions › Séparer les locuteurs »\n"
            "  télécharge une seule fois un petit module (~50 Mo, depuis GitHub, sans compte)\n"
            "  et affiche ensuite « — Locuteur 1 : … », « — Locuteur 2 : … » dans tes réunions.\n"
            "  Tout reste sur ton Mac. Indique le nombre de personnes dans « Locuteurs\n"
            "  attendus » si tu le connais (sinon « Automatique »). La séparation est fiable\n"
            "  sur des voix distinctes et se dégrade quand plusieurs parlent en même temps.\n"
            "• Une seule transcription à la fois : pendant un import ou une réunion, on ne\n"
            "  peut pas en lancer une autre (un message le rappelle).\n"
            "\n"
            "━━━ 4. L'INDICATEUR DANS LA BARRE DES MENUS ━━━\n"
            "\n"
            "L'icône (un micro blanc) change de FORME selon l'état :\n"
            "   • micro fin (contour) ........ le moteur se charge\n"
            "   • micro plein ................ prêt\n"
            "   • pastille d'enregistrement .. ENREGISTRE (le micro est actif !)\n"
            "   • forme d'onde ............... transcrit (réunion, dictée OU import)\n"
            "   • presse-papiers ............. écrit le texte\n"
            "Pendant un import de fichier, le menu « Réunions » affiche aussi la\n"
            "progression (« Transcription du fichier… NN % »), et pendant la\n"
            "transcription d'une réunion, l'item « Démarrer une réunion » devient\n"
            "« Annuler la transcription… NN % ».\n"
            "Quand l'icône est sur « enregistre », le micro tourne : ne l'oublie pas.\n"
            "Sur un MacBook, l'icône peut se cacher derrière l'encoche de la caméra :\n"
            "réduis le nombre d'icônes voisines si tu ne la vois pas.\n"
            "\n"
            "Quand tu CHANGES de qualité, l'icône revient au micro « fin » (chargement)\n"
            "le temps de préparer le nouveau modèle. La TOUTE PREMIÈRE fois qu'on choisit\n"
            "une qualité, le modèle est TÉLÉCHARGÉ (jusqu'à ~1 min ; le « medium » fait\n"
            "~1,5 Go) — un message le signale. Ensuite c'est en cache et bien plus rapide.\n"
            "Un message « Modèle prêt ✓ » confirme quand tu peux dicter.\n"
            "\n"
            "━━━ 5. L'HISTORIQUE ━━━\n"
            "\n"
            "• Toutes les transcriptions (éclair ET réunions) s'ajoutent à\n"
            "  « Historique récent ». Conservé après fermeture (base locale,\n"
            "  1000 dernières entrées).\n"
            "• Clique une entrée pour la rouvrir : tu peux la lire, la MODIFIER, puis\n"
            "  « Copier », « Enregistrer les modifications » (cela crée une NOUVELLE\n"
            "  entrée — l'originale n'est pas écrasée) ou « Supprimer ».\n"
            "• « Réunions › Exporter la dernière réunion (.txt) » et « Exporter tout\n"
            "  l'historique (.txt) » créent des fichiers DATÉS dans :\n"
            "     ~/Documents/VoixFlash Transcriptions\n"
            "\n"
            "━━━ 6. LES RÉGLAGES ━━━\n"
            "\n"
            f"• Qualité / vitesse : Rapide (tiny) → Très précis (medium). Actuel : {model}.\n"
            "  1er choix d'une qualité = téléchargement unique (voir section 4). Astuce :\n"
            "  pour une dictée courte et claire en français, « tiny » est souvent déjà\n"
            "  excellent ET très rapide ; les gros modèles aident surtout sur le bruit,\n"
            "  les accents, le vocabulaire rare et les mots anglais.\n"
            f"• Langue : Français / Anglais / Automatique. Actuel : {lang}.\n"
            "   – « Automatique » détecte la langue à chaque dictée : idéal pour ALTERNER\n"
            "     français et anglais. En réunion c'est très fiable ; pour une dictée\n"
            "     éclair très courte (1-2 mots), la détection a peu de matière et peut se\n"
            "     tromper — dans ce cas, fixe Français ou Anglais.\n"
            "   – MÉLANGER les deux langues DANS la même phrase n'est pas bien géré par le\n"
            "     moteur (il choisit une langue dominante) ; un modèle plus gros aide un peu.\n"
            f"• Touche de dictée : préréglages (Option droite, Cmd droite, Ctrl droite,\n"
            f"  F5) OU « Choisir ma touche… » qui capte la touche que TU presses (le plus\n"
            f"  fiable, quel que soit le clavier). Actuel : {hk}. Effet immédiat.\n"
            f"• Réunions › Horodatage des passages : ajoute [mm:ss]. Actuel : {ts_state}.\n"
            "• Texte dicté › Ajouter un mot au vocabulaire… : écris un nom propre, une\n"
            "  marque ou un terme métier tel que tu veux le voir. Les variantes proches\n"
            "  seront corrigées, même quand le moteur découpe le mot (« voie flash »\n"
            "  devient « VoixFlash »). C'est LE réglage qui change tout sur les noms.\n"
            "• Texte dicté › Corriger une faute récurrente… : remplacement exact, de la\n"
            "  version fautive vers la bonne. Sert aussi de raccourci de saisie : une\n"
            "  phrase courte qui se transforme en un texte plus long (signature, adresse).\n"
            "• Texte dicté › Ouvrir le fichier de vocabulaire… : édition en masse.\n"
            "  Toute modification prend effet à la dictée suivante, sans redémarrage.\n"
            f"• Texte dicté › Retirer les hésitations : efface les « euh » et « hmm ».\n"
            f"  Actuel : {hesit_state}.\n"
            f"• Retour sonore : un son au début et à la fin de chaque dictée, pour savoir\n"
            f"  sans regarder l'écran que le micro écoute. Actuel : {sound_state}.\n"
            "  Le son de départ arrive quand le micro capte VRAIMENT : attends-le avant\n"
            "  de parler, c'est ce qui évite de perdre le premier mot. Rien n'est joué\n"
            "  sur un casque Bluetooth (cela le ferait passer en qualité téléphone).\n"
            "\n"
            "━━━ 7. AUTORISATIONS (à faire une seule fois) ━━━\n"
            "\n"
            "Active VoixFlash (il apparaît sous le nom « Python ») dans Réglages ›\n"
            "Confidentialité, via les boutons « Ouvrir réglages › … » de ce menu :\n"
            "   1) Microphone — pour t'entendre\n"
            "   2) Accessibilité — pour coller le texte (Cmd+V)\n"
            "   3) Surveillance des entrées — pour la touche de dictée\n"
            "Puis clique « Redémarrer VoixFlash ». Tant que « Surveillance des entrées »\n"
            "n'est pas accordée, la touche de dictée reste sans effet (et sans message).\n"
            "\n"
            "Si la touche cesse de répondre APRÈS avoir fonctionné, utilise « Aide &\n"
            "autorisations › La touche de dictée ne répond plus ? ». Il distingue les\n"
            "trois causes qui se ressemblent de l'extérieur : autorisation perdue,\n"
            "écoute arrêtée, et saisie sécurisée (un champ mot de passe ouvert quelque\n"
            "part suffit à ce que macOS cesse de transmettre les touches). Indice :\n"
            "si Option marche encore mais que F5 ne fait rien, c'est ce dernier cas.\n"
            "\n"
            "━━━ 8. HORS-LIGNE & VIE PRIVÉE ━━━\n"
            "\n"
            "Après l'installation, tout fonctionne SANS internet : ta voix ne quitte\n"
            "jamais ton Mac. Aucun compte, aucun abonnement, aucune clé.\n"
            "\n"
            "Journal technique (en cas de souci) :\n"
            "   ~/Library/Application Support/VoixFlash/voixflash.log"
        )

        try:
            app_to_front()
            win = rumps.Window(
                title="VoixFlash — Mode d'emploi",
                message="Fais défiler pour tout lire. Ce panneau est informatif "
                        "(rien à saisir) ; clique « Fermer » quand tu as terminé.",
                default_text=guide,
                ok="Fermer",
                dimensions=(540, 460),   # champ déroulant : tout le guide tient dedans
            )
            win.run()
        except Exception as e:
            log(f"fenêtre guide : {e}")

    def diagnose_hotkey(self, _sender):
        """Explique pourquoi la touche de dictée reste muette, et répare ce qui peut l'être.

        Les trois causes réelles se ressemblent de l'extérieur (« rien ne se passe »)
        mais se distinguent très bien de l'intérieur, d'où ce point unique."""
        acc = accessibility_trusted()
        alive = bool(self._listener is not None and self._listener.is_alive())
        secure = secure_input_enabled()
        modifier = hotkey_is_modifier(self._hotkey)
        lignes = [
            f"Touche actuelle : {self._current_hotkey_label()}"
            f" ({'modificateur' if modifier else 'touche ordinaire'})",
            f"Écoute clavier active : {'oui' if alive else 'NON'}",
            f"Autorisation « Accessibilité » : {'accordée' if acc else 'MANQUANTE'}",
            f"Saisie sécurisée en cours : "
            f"{'inconnue' if secure is None else ('OUI' if secure else 'non')}",
            "",
        ]
        if secure:
            lignes += [
                "→ Une application a activé la SAISIE SÉCURISÉE (champ mot de passe "
                "ouvert, ou « saisie sécurisée » cochée dans le Terminal). Tant qu'elle "
                "est active, macOS n'envoie plus les appuis de touches à VoixFlash.",
                "",
                "Ferme le champ mot de passe, ou décoche Terminal › menu Terminal › "
                "« Saisie sécurisée ». Si le problème persiste, ferme puis rouvre "
                "l'application où tu tapais un mot de passe.",
            ]
        elif not acc:
            lignes += ["→ Autorise « Accessibilité » (bouton de ce menu), puis "
                       "« Redémarrer VoixFlash »."]
        elif not alive:
            lignes += ["→ L'écoute clavier s'est arrêtée. Elle vient d'être relancée."]
        else:
            lignes += [
                "→ Tout paraît normal de ce côté. Si la touche reste muette, c'est "
                "presque toujours l'autorisation « Surveillance des entrées » qui a "
                "expiré (elle le fait après une veille ou une mise à jour).",
                "",
                "Indice utile : si un raccourci fait d'un simple modificateur (Option) "
                "fonctionne alors qu'une touche ordinaire (F5) ne fait rien, c'est "
                "exactement ce cas.",
                "",
                "L'écoute vient d'être réarmée : réessaie tout de suite.",
            ]
        if not secure and acc:
            self._rearm_listener("diagnostic manuel")
        self._show_info("Diagnostic de la touche de dictée", "\n".join(lignes))

    def show_path(self, _sender):
        # On affiche le chemin STABLE du lanceur (celui que launchd utilise), pas le
        # realpath profond sous ~/.local/share/uv qui change à chaque mise à jour de uv.
        # Dans la liste de macOS, l'entrée apparaît sous le nom « Python ».
        self._modal_alert(
            title="Autorisations VoixFlash",
            message="Dans Réglages › Confidentialité, l'entrée à activer apparaît sous "
                    "le nom « Python ». Active-la pour :\n"
                    "  • Microphone\n  • Accessibilité\n  • Surveillance des entrées\n\n"
                    "Normalement, tu n'as RIEN à ajouter à la main : utilise les boutons "
                    "« Ouvrir réglages › … » de ce menu, qui déclenchent la demande.\n\n"
                    "Si tu dois vraiment l'ajouter manuellement (bouton +), vise ce fichier :\n"
                    f"{sys.executable}",
            ok="OK",
        )

    def open_mic_settings(self, _sender):
        # On (re)déclenche la demande d'accès : ça garantit que VoixFlash apparaît
        # bien dans la liste « Microphone » que l'utilisateur va ouvrir juste après.
        threading.Thread(target=self._prime_microphone, kwargs={"force": True}, daemon=True).start()
        self._run([OPEN, "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"])

    def open_acc_settings(self, _sender):
        self._run([OPEN, "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])

    def open_input_settings(self, _sender):
        self._run([OPEN, "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"])

    def _show_welcome(self):
        self._modal_alert(
            title="Bienvenue dans VoixFlash 🎙️",
            message="Avant la première utilisation, autorise 3 choses dans les réglages "
                    "du Mac (menu « Aide & autorisations ») :\n\n"
                    "1) Microphone — pour entendre ta voix\n"
                    "2) Accessibilité — pour coller le texte (Cmd+V)\n"
                    "3) Surveillance des entrées — pour la touche de dictée\n\n"
                    "Ensuite, clique « Redémarrer VoixFlash ».\n\n"
                    f"Dictée éclair : maintiens la touche « {self._current_hotkey_label()} », parle, relâche.",
            ok="J'ai compris",
        )

    # --------------------------------------------------------------- divers --
    def restart_app(self, _sender):
        """Relance l'application (utile après avoir accordé des autorisations)."""
        if self._recording:
            ok = self._modal_alert(
                title="Enregistrement en cours",
                message="Un enregistrement est en cours. Si tu redémarres maintenant, il "
                        "sera CONSERVÉ sur le disque et VoixFlash te proposera de le "
                        "transcrire au prochain démarrage.\n\nRedémarrer ?",
                ok="Redémarrer", cancel="Annuler",
            )
            if ok != 1:
                return
            try:
                self._abort_recording()     # libère le micro, garde l'audio
            except Exception as e:
                log(f"arrêt avant redémarrage : {e}")
        try:
            if self._listener:
                self._listener.stop()
        except Exception:
            pass
        log("Redémarrage demandé.")
        # Sur une app de barre des menus, os.execv laisse parfois un emplacement
        # « fantôme » (la case reste réservée, mais l'icône ne revient jamais), car
        # le serveur de fenêtres garde l'ancien NSStatusItem. On préfère donc demander
        # à launchd de tuer puis relancer proprement le service (nouveau processus,
        # nouvelle icône). Repli sur os.execv si launchd n'est pas disponible.
        if not self._relaunch_via_launchd():
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def _relaunch_via_launchd(self):
        """Relance le service via launchd (kickstart -k). Renvoie True si la commande a
        été acceptée : launchd va alors arrêter ce processus et en démarrer un neuf."""
        # On ne kickstart QUE si CE processus est bien celui géré par launchd. Sinon
        # (lancement manuel/dev pendant que l'agent est chargé), kickstart relancerait
        # l'AUTRE instance et on se retrouverait avec deux icônes et deux écoutes
        # clavier en conflit. launchd définit XPC_SERVICE_NAME = étiquette de l'agent.
        if os.environ.get("XPC_SERVICE_NAME") != LAUNCHD_LABEL:
            log("Pas lancé par launchd (XPC_SERVICE_NAME ≠ étiquette) → repli sur os.execv.")
            return False
        try:
            uid = os.getuid()
            r = subprocess.run(
                ["/bin/launchctl", "kickstart", "-k", f"gui/{uid}/{LAUNCHD_LABEL}"],
                capture_output=True, check=False, timeout=10,
            )
            if r.returncode == 0:
                log("Redémarrage via launchd (kickstart -k).")
                return True
            log(f"kickstart rc={r.returncode} : {r.stderr.decode('utf-8', 'replace').strip()}")
        except Exception as e:
            log(f"kickstart : {e}")
        return False

    def quit_app(self, _sender):
        # Enregistrement en cours : on demande confirmation, puis on coupe le micro en
        # GARDANT l'audio sur le disque (reproposé au prochain démarrage).
        if self._recording:
            if self._modal_alert(
                    title="Enregistrement en cours",
                    message="Un enregistrement est en cours. Si tu quittes maintenant, il "
                            "sera CONSERVÉ et te sera proposé au prochain démarrage.\n\n"
                            "Quitter ?",
                    ok="Quitter", cancel="Annuler") != 1:
                return
            try:
                self._abort_recording()
            except Exception as e:
                log(f"arrêt avant fermeture : {e}")
        elif self._transcribing:
            if self._modal_alert(
                    title="Transcription en cours",
                    message="Une transcription est en cours et sera perdue si tu quittes "
                            "maintenant.\n\nQuitter quand même ?",
                    ok="Quitter", cancel="Annuler") != 1:
                return
        try:
            if self._listener:
                self._listener.stop()
        except Exception:
            pass
        log("Quitter.")
        rumps.quit_application()


if __name__ == "__main__":
    try:
        VoixFlashApp().run()
    except Exception as e:
        log(f"FATAL : {e}")
        raise
