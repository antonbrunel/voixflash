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
import sys
import json
import time
import queue
import sqlite3
import contextlib
import threading
import subprocess
import datetime

import numpy as np
import sounddevice as sd
import rumps
from pynput import keyboard
from faster_whisper import WhisperModel

# Cacher l'icône du Dock : VoixFlash est une application "accessoire", visible
# uniquement dans la barre des menus en haut de l'écran.
try:
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
except Exception:  # au cas où AppKit ne serait pas disponible
    NSApplication = None
    NSApplicationActivationPolicyAccessory = None

# Pour afficher une fenêtre modale au tour de boucle suivant, sans bloquer la
# boucle de rafraîchissement de l'interface.
try:
    from PyObjCTools import AppHelper
except Exception:
    AppHelper = None


# --------------------------------------------------------------------------- #
#  Chemins & constantes
# --------------------------------------------------------------------------- #
APP_NAME = "VoixFlash"
LAUNCHD_LABEL = "com.voixflash.agent"   # étiquette du LaunchAgent (cf. install.command)
APP_HOME = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
CONFIG_PATH = os.path.join(APP_HOME, "config.json")
HISTORY_PATH = os.path.join(APP_HOME, "history.json")   # ancien format (migré vers SQLite)
HISTORY_DB = os.path.join(APP_HOME, "history.db")       # historique : base SQLite (scalable)
HISTORY_KEEP = 1000   # nombre max d'entrées conservées (purge auto des plus anciennes)
LOG_PATH = os.path.join(APP_HOME, "voixflash.log")
TRANSCRIPTS_DIR = os.path.expanduser(f"~/Documents/{APP_NAME} Transcriptions")

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

os.makedirs(APP_HOME, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

# Réglages par défaut (modifiables depuis le menu, sauvegardés dans config.json).
DEFAULT_CONFIG = {
    "hotkey": "alt_r",            # touche de dictée éclair = Option (alt) droite
    "model": "small",            # qualité/vitesse de transcription (défaut équilibré)
    "language": "fr",            # langue : "fr" ou "en"
    "meeting_timestamps": False,  # ajouter [mm:ss] devant chaque passage des réunions
    "restore_clipboard": True,    # remettre l'ancien presse-papiers après le collage
    "beam_size": 5,              # qualité du décodage (5 = bon compromis)
    "mic_primed": False,         # le micro a-t-il déjà été « amorcé » (demande d'autorisation déclenchée) ?
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


def parse_hotkey(s):
    """Transforme une chaîne de config ('alt_r', 'f5', 'a'...) en touche pynput."""
    s = (s or "").strip().lower()
    if hasattr(keyboard.Key, s):                # touche spéciale (alt_r, f5, cmd_r...)
        return getattr(keyboard.Key, s)
    if len(s) == 1:                             # touche caractère normale
        return keyboard.KeyCode.from_char(s)
    return keyboard.Key.alt_r                   # repli sûr : Option droite


def key_matches(key, target):
    """Compare une touche reçue à la touche de dictée configurée."""
    try:
        if isinstance(target, keyboard.Key):
            return key == target
        # KeyCode (touche caractère) : on compare le caractère
        if getattr(key, "char", None) is not None and getattr(target, "char", None) is not None:
            return key.char == target.char
        return key == target
    except Exception:
        return False


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
    """Crée la table si besoin, puis migre une seule fois l'ancien history.json."""
    try:
        with _hist_db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS entries ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " ts TEXT NOT NULL,"
                " mode TEXT NOT NULL,"
                " text TEXT NOT NULL)")
        _history_migrate_json()
    except Exception as e:
        log(f"history_init : {e}")


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
        self.model_name_loaded = None
        self._state = "loading"
        self._recording = False
        self._record_mode = None          # "flash" ou "meeting"
        self._ptt_active = False          # touche de dictée actuellement maintenue ?
        self._stream = None               # flux audio en cours
        self._frames = []                 # morceaux audio enregistrés
        self._record_sr = 16000           # fréquence d'échantillonnage utilisée
        self._record_start = None         # début de l'enregistrement (garde-fou durée)
        self._last_listener_restart = 0.0  # anti-rafale pour la relance de l'écoute
        self._ui_queue = queue.Queue()    # messages des threads de fond vers l'UI
        self._lock = threading.Lock()
        self._hotkey = parse_hotkey(self.config["hotkey"])
        self._listener = None

        # Construction du menu
        self._build_menu()

        # Le minuteur tourne sur le thread principal : c'est LUI (et lui seul) qui
        # touche à l'interface, à partir des messages déposés par les threads de fond.
        # 0,15 s = indicateur réactif, et coût processeur négligeable au repos.
        self._timer = rumps.Timer(self._drain_ui, 0.15)
        self._timer.start()

        # Chargement du modèle en arrière-plan → démarrage instantané de l'app.
        threading.Thread(target=self._load_model, daemon=True).start()

        # Amorce du micro (une seule fois) : ouvre brièvement l'entrée audio pour
        # DÉCLENCHER la demande d'autorisation macOS. Sans ça, « Python » n'apparaît
        # jamais dans Réglages › Confidentialité › Microphone et reste impossible à cocher.
        threading.Thread(target=self._prime_microphone, daemon=True).start()

        # Écoute clavier globale pour la dictée éclair.
        self._start_listener()

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

    # ----------------------------------------------------------------- menu --
    def _build_menu(self):
        self.meeting_item = rumps.MenuItem(MEETING_START_TITLE, callback=self.toggle_meeting)
        self.history_menu = rumps.MenuItem("Historique récent")
        self.reunions_menu = rumps.MenuItem("Réunions")
        self.quality_menu = rumps.MenuItem("Qualité / vitesse")
        self.lang_menu = rumps.MenuItem("Langue")
        self.hotkey_menu = rumps.MenuItem("Touche de dictée")
        self.ts_item = rumps.MenuItem("Horodatage des passages", callback=self.toggle_timestamps)
        self.restore_item = rumps.MenuItem("Restaurer le presse-papiers après une dictée",
                                           callback=self.toggle_restore)
        self.help_menu = rumps.MenuItem("Aide & autorisations")

        self.menu = [
            self.meeting_item,
            rumps.separator,
            self.history_menu,
            rumps.separator,
            self.reunions_menu,
            self.quality_menu,
            self.lang_menu,
            self.hotkey_menu,
            self.restore_item,
            rumps.separator,
            self.help_menu,
            rumps.MenuItem("Redémarrer VoixFlash", callback=self.restart_app),
            rumps.MenuItem("Quitter", callback=self.quit_app),
        ]

        # Sous-menu « Réunions » : actions et réglages propres aux réunions.
        self.reunions_menu.add(rumps.MenuItem("Exporter la dernière réunion (.txt)",
                                              callback=self.export_last_meeting))
        self.reunions_menu.add(self.ts_item)

        # Remplissage des sous-menus
        self._refresh_quality_menu()
        self._refresh_lang_menu()
        self._refresh_hotkey_menu()
        self._refresh_history_menu()
        self.ts_item.state = bool(self.config["meeting_timestamps"])
        self.restore_item.state = bool(self.config["restore_clipboard"])

        # Sous-menu d'aide : guide complet en tête, puis liens vers les réglages macOS.
        self.help_menu.add(rumps.MenuItem("Mode d'emploi complet", callback=self.show_guide))
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
        for label, val in [("Français", "fr"), ("Anglais", "en")]:
            item = rumps.MenuItem(label, callback=self._make_lang_cb(val))
            item.state = (self.config["language"] == val)
            self.lang_menu.add(item)

    def _refresh_hotkey_menu(self):
        self._safe_clear(self.hotkey_menu)
        for label, val in HOTKEY_CHOICES:
            item = rumps.MenuItem(label, callback=self._make_hotkey_cb(val))
            item.state = (self.config["hotkey"] == val)
            self.hotkey_menu.add(item)

    def _refresh_history_menu(self):
        """Reconstruit le sous-menu d'historique : entrées récentes cliquables (→ fenêtre
        de transcription), puis export et vidage. À appeler sur le thread principal."""
        self._safe_clear(self.history_menu)
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
    def _make_quality_cb(self, val):
        def cb(_sender):
            self.config["model"] = val
            save_json(CONFIG_PATH, self.config)
            self._refresh_quality_menu()
            threading.Thread(target=self._load_model, daemon=True).start()
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
                self.config["hotkey"] = val
                save_json(CONFIG_PATH, self.config)
                self._hotkey = parse_hotkey(val)
                self._ptt_active = False
                self._refresh_hotkey_menu()
                # Retour RÉELLEMENT visible (les notifications macOS ne marchent pas hors
                # bundle) : on ouvre l'alerte au tour de boucle suivant pour ne pas la
                # déclencher pendant que le menu est encore en cours de fermeture.
                self._present(self._show_info, "Touche changée",
                              f"Dictée éclair : {self._hotkey_label(val)}")
            except Exception as e:
                log(f"changement de touche : {e}")
        return cb

    def _hotkey_label(self, val):
        for label, v in HOTKEY_CHOICES:
            if v == val:
                return label
        return val

    def _make_history_cb(self, entry_id):
        """Clic sur une entrée d'historique → ouvre sa fenêtre de transcription."""
        def cb(_sender):
            entry = history_get(entry_id)
            if entry is None:
                self._present(self._show_error, "Cette entrée n'existe plus.")
                return
            self._present(self._show_transcript, entry)
        return cb

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
    def _load_model(self):
        """Charge (ou recharge) le moteur de transcription, en arrière-plan."""
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
            try:
                model = WhisperModel(name, device="cpu", compute_type="int8",
                                     local_files_only=True)
                log(f"Modèle chargé depuis le cache : {name}")
            except Exception as cache_miss:
                # Modèle pas encore téléchargé (tout premier usage de cette qualité) :
                # on autorise alors le téléchargement réseau, une seule fois.
                log(f"Modèle « {name} » absent du cache ({cache_miss}) — téléchargement…")
                model = WhisperModel(name, device="cpu", compute_type="int8")
                log(f"Modèle téléchargé puis chargé : {name}")
            with self._lock:
                self.model = model
                self.model_name_loaded = name
        except Exception as e:
            log(f"Erreur de chargement du modèle '{name}' : {e}")
            self._ui_queue.put(("error", f"Impossible de charger le modèle « {name} » : {e}"))
        finally:
            if not self._recording:
                self._ui_queue.put(("state", "idle"))

    # --------------------------------------------------------- écoute clavier --
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
            # On ignore la répétition automatique tant que la touche reste maintenue.
            if self._ptt_active:
                return
            if not key_matches(key, self._hotkey):
                return
            if self._recording:               # une réunion est déjà en cours
                return
            if self.model is None:            # le moteur n'est pas encore prêt
                self._ui_queue.put(("error", "Le moteur de transcription se charge encore, réessaie dans un instant."))
                return
            self._ptt_active = True
            self._start_recording("flash")
        except Exception as e:
            log(f"_on_press : {e}")
            self._ptt_active = False

    def _on_release(self, key):
        try:
            if not self._ptt_active:
                return
            if not key_matches(key, self._hotkey):
                return
            self._ptt_active = False
            self._stop_recording()
        except Exception as e:
            log(f"_on_release : {e}")
            self._ptt_active = False

    # ------------------------------------------------------------ audio I/O --
    def _start_recording(self, mode):
        """Démarre l'enregistrement. Renvoie True si le micro s'est bien ouvert."""
        with self._lock:
            if self._recording:
                return False
            self._recording = True
            self._record_mode = mode
            self._frames = []
            self._record_start = time.monotonic()
        self._ui_queue.put(("state", "recording"))
        # On enregistre en int16 (PCM standard, 2 octets/échantillon) : moitié moins
        # de mémoire qu'en float32 pour les longues réunions. La conversion en
        # float32 [-1, 1] attendu par Whisper se fait une seule fois à l'arrêt.
        # On tente 16 kHz directement (CoreAudio convertit proprement) ; en cas
        # d'échec, on enregistre à la fréquence du micro puis on rééchantillonne.
        try:
            self._record_sr = 16000
            self._stream = sd.InputStream(samplerate=16000, channels=1,
                                          dtype="int16", callback=self._audio_cb)
            self._stream.start()
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
            try:
                self._stream = sd.InputStream(samplerate=self._record_sr, channels=1,
                                              dtype="int16", callback=self._audio_cb)
                self._stream.start()
                return True
            except Exception as e2:
                log(f"Impossible d'ouvrir le micro : {e2}")
                with self._lock:
                    self._recording = False
                    self._record_mode = None
                self._ui_queue.put(("error", "Impossible d'accéder au micro. Autorise le « Microphone » dans les réglages, puis « Redémarrer VoixFlash »."))
                self._ui_queue.put(("state", "idle"))
                return False

    def _audio_cb(self, indata, frames, time_info, status):
        if status:
            log(f"audio status: {status}")
        # Copie nécessaire : le tampon est réutilisé par PortAudio.
        self._frames.append(indata.copy())

    def _stop_recording(self):
        # Tout se fait sous le verrou. Le callback audio (_audio_cb) ne prend JAMAIS
        # le verrou : fermer le flux ici ne peut donc pas créer d'inter-blocage, et
        # comme stop() attend la fin du callback, on récupère ensuite la totalité des
        # échantillons sans rien perdre, et sans qu'un nouvel enregistrement puisse
        # s'intercaler et écraser les buffers.
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            mode = self._record_mode
            self._record_mode = None
            self._record_start = None
            stream = self._stream
            self._stream = None
            record_sr = self._record_sr
            try:
                if stream is not None:
                    stream.stop()    # attend la fin des callbacks (plus aucun ajout)
                    stream.close()
            except Exception as e:
                log(f"fermeture flux : {e}")
            frames = self._frames    # capturé après stop() : complet
            self._frames = []

        if frames:
            # int16 -> float32 normalisé dans [-1, 1], ce qu'attend Whisper.
            audio = np.concatenate(frames, axis=0).flatten().astype(np.float32) / 32768.0
        else:
            audio = np.zeros(0, dtype=np.float32)

        self._ui_queue.put(("state", "transcribing"))
        # La transcription tourne dans un thread séparé : l'interface ne fige pas.
        threading.Thread(target=self._process_audio,
                         args=(audio, record_sr, mode), daemon=True).start()

    def _resample(self, audio, sr_in, sr_out=16000):
        """Rééchantillonnage simple (interpolation linéaire), utilisé en repli."""
        if sr_in == sr_out or len(audio) == 0:
            return audio
        n_out = int(round(len(audio) * sr_out / sr_in))
        if n_out <= 0:
            return np.zeros(0, dtype=np.float32)
        x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        return np.interp(x_new, x_old, audio).astype(np.float32)

    # ----------------------------------------------------- transcription --
    def _process_audio(self, audio, sr, mode):
        try:
            if sr != 16000 and len(audio) > 0:
                audio = self._resample(audio, sr, 16000)
            if len(audio) < 1600:          # moins de 0,1 s : rien à transcrire
                self._ui_queue.put(("state", "idle"))
                return

            with self._lock:
                model = self.model
            if model is None:
                self._ui_queue.put(("error", "Moteur de transcription indisponible."))
                self._ui_queue.put(("state", "idle"))
                return

            # vad_filter (détection de voix) seulement pour les réunions : il évite
            # de transcrire les longs silences. En dictée éclair on parle exprès,
            # donc on le désactive pour ne jamais perdre un mot.
            # condition_on_previous_text=False : évite les répétitions en boucle.
            segments, info = model.transcribe(
                audio,
                language=self.config["language"],
                beam_size=int(self.config.get("beam_size", 5)),
                vad_filter=(mode == "meeting"),
                condition_on_previous_text=False,
            )
            seglist = list(segments)

            if mode == "meeting" and self.config["meeting_timestamps"]:
                # L'horodatage est fourni gratuitement par faster-whisper (start de
                # chaque segment) : on l'ajoute seulement si l'option est activée.
                text = "\n".join(f"[{fmt_ts(s.start)}] {s.text.strip()}" for s in seglist).strip()
            else:
                text = " ".join(s.text.strip() for s in seglist).strip()

            # Garde-fou anti-hallucination (silence/bruit) : on n'écrit rien.
            if is_probably_hallucination(text):
                log(f"Transcription écartée (probable hallucination) : {text!r}")
                text = ""

            if not text:
                # Aucun texte reconnu. En dictée éclair on reste silencieux (rien à
                # coller). En réunion, l'utilisateur a cliqué « Démarrer » puis
                # « Arrêter » : il ATTEND un résultat — un retour vide passerait pour
                # une réunion perdue. On l'informe explicitement.
                if mode == "meeting":
                    self._ui_queue.put(("error", "Réunion terminée, mais aucun texte n'a "
                                                 "été détecté (micro trop faible, trop loin, "
                                                 "ou silence). Rien n'a été enregistré."))
                self._ui_queue.put(("state", "idle"))
                return

            # Écriture en base depuis ce thread de fond : history_add ouvre sa propre
            # connexion SQLite, c'est sûr. On demande ensuite au thread principal de
            # rafraîchir le menu (« history_changed »).
            entry = history_add(mode, text)
            self._ui_queue.put(("history_changed", None))

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
            self._ui_queue.put(("error", f"Erreur de transcription : {e}"))
            self._ui_queue.put(("state", "idle"))

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
        old = self._get_clipboard_bytes() if self.config["restore_clipboard"] else None
        self._set_clipboard(text)
        time.sleep(0.12)        # court délai pour que tout soit prêt avant le collage
        self._send_cmd_v()
        # On ne restaure que s'il y avait réellement du texte : on évite ainsi
        # d'effacer une image ou un fichier qui aurait été copié auparavant.
        if old is not None and old.strip():
            time.sleep(0.6)     # bien après que le collage a eu lieu
            self._run([PBCOPY], input=old, env=CLIP_ENV, timeout=5)

    def _send_cmd_v(self):
        """Simule l'appui Cmd+V (nécessite l'autorisation Accessibilité)."""
        try:
            from Quartz import (
                CGEventCreateKeyboardEvent, CGEventPost, CGEventSetFlags,
                kCGHIDEventTap, kCGEventFlagMaskCommand,
            )
            V_KEYCODE = 9  # code de la touche « v »
            down = CGEventCreateKeyboardEvent(None, V_KEYCODE, True)
            CGEventSetFlags(down, kCGEventFlagMaskCommand)
            up = CGEventCreateKeyboardEvent(None, V_KEYCODE, False)
            CGEventSetFlags(up, kCGEventFlagMaskCommand)
            CGEventPost(kCGHIDEventTap, down)
            CGEventPost(kCGHIDEventTap, up)
        except Exception as e:
            log(f"Cmd+V : {e}")
            self._ui_queue.put(("error", "Collage impossible : autorise « Accessibilité » dans les réglages."))

    # --------------------------------------------- boucle UI (thread principal) --
    def _drain_ui(self, _timer):
        """Appelée par le minuteur sur le thread principal : applique les changements d'UI."""
        try:
            while True:
                try:
                    kind, payload = self._ui_queue.get_nowait()
                except queue.Empty:
                    break

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
                elif kind == "error":
                    self._present(self._show_error, payload)
                elif kind == "welcome":
                    self._present(self._show_welcome)
        except Exception as e:
            log(f"drain UI : {e}")

    def _present(self, func, *args):
        """Affiche une fenêtre modale au tour de boucle SUIVANT : le drain rend la main
        tout de suite et l'indicateur ne reste pas figé pendant qu'on prépare la fenêtre."""
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

    def _show_error(self, msg):
        """Affiche une erreur de façon TOUJOURS visible (alerte, marche sans bundle)."""
        try:
            rumps.alert(title=APP_NAME, message=msg, ok="OK")
        except Exception as e:
            log(f"alerte erreur : {e} — {msg}")

    def _show_info(self, title, msg):
        """Petite information visible (les notifications macOS ne marchent pas hors bundle)."""
        try:
            rumps.alert(title=title, message=msg, ok="OK")
        except Exception as e:
            log(f"alerte info : {e} — {title} : {msg}")

    def _confirm(self, msg, ok="Confirmer", cancel="Annuler"):
        """Demande une confirmation. Renvoie True si l'utilisateur valide."""
        try:
            return bool(rumps.alert(title=APP_NAME, message=msg, ok=ok, cancel=cancel))
        except Exception as e:
            log(f"confirmation : {e}")
            return False

    # ------------------------------------------------------------- actions menu --
    def toggle_meeting(self, sender):
        """Démarre / arrête l'enregistrement long d'une réunion."""
        # Lecture cohérente de l'état partagé (sans garder le verrou pendant les
        # actions, qui le reprennent elles-mêmes).
        with self._lock:
            recording = self._recording
            mode = self._record_mode
        if recording and mode == "flash":
            return  # une dictée éclair est en cours, on ne touche à rien
        if not recording:
            if self.model is None:
                self._present(self._show_error, "Le moteur de transcription se charge encore, réessaie dans un instant.")
                return
            # On ne met le titre « Arrêter » que si le micro s'est réellement ouvert.
            if self._start_recording("meeting"):
                sender.title = MEETING_STOP_TITLE
        else:
            sender.title = MEETING_START_TITLE
            self._stop_recording()

    def toggle_timestamps(self, sender):
        self.config["meeting_timestamps"] = not self.config["meeting_timestamps"]
        sender.state = self.config["meeting_timestamps"]
        save_json(CONFIG_PATH, self.config)

    def toggle_restore(self, sender):
        self.config["restore_clipboard"] = not self.config["restore_clipboard"]
        sender.state = self.config["restore_clipboard"]
        save_json(CONFIG_PATH, self.config)

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
        try:
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

    # ------------------------------------------------------ aide & autorisations --
    def show_guide(self, _sender):
        """Mode d'emploi complet : rassemble toutes les règles utiles (y compris les
        comportements implicites), dans une fenêtre déroulante. Le texte s'adapte aux
        réglages actuels (touche, presse-papiers, modèle, langue, horodatage)."""
        hk = self._hotkey_label(self.config.get("hotkey", "alt_r"))
        restore_on = bool(self.config.get("restore_clipboard", True))
        restore_state = "activé" if restore_on else "désactivé"
        model_labels = {val: label for label, val in MODEL_CHOICES}
        model = model_labels.get(self.config.get("model", "small"), self.config.get("model", "small"))
        lang = "Français" if self.config.get("language", "fr") == "fr" else "Anglais"
        ts_state = "activé" if self.config.get("meeting_timestamps") else "désactivé"

        guide = (
            "VOIXFLASH — MODE D'EMPLOI COMPLET\n"
            "\n"
            "━━━ 1. LES DEUX FAÇONS DE DICTER ━━━\n"
            "\n"
            "• DICTÉE ÉCLAIR (partout)\n"
            "  Place ton curseur dans n'importe quel champ de texte.\n"
            f"  Maintiens la touche « {hk} », parle, puis RELÂCHE.\n"
            "  Le texte s'écrit tout seul à l'endroit du curseur.\n"
            "  (Maintien = on parle ; relâché = ça écrit. Une pression très brève\n"
            "  ne dicte rien.)\n"
            "\n"
            "• RÉUNION (enregistrement long)\n"
            "  Menu › « Démarrer une réunion ». Parle aussi longtemps que tu veux.\n"
            "  Menu › « Arrêter la réunion » : le texte s'affiche dans une fenêtre\n"
            "  DANS l'application — il n'est PAS collé ailleurs.\n"
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
            "\n"
            "━━━ 4. L'INDICATEUR DANS LA BARRE DES MENUS ━━━\n"
            "\n"
            "L'icône (un micro blanc) change de FORME selon l'état :\n"
            "   • micro fin (contour) ........ le moteur se charge\n"
            "   • micro plein ................ prêt\n"
            "   • pastille d'enregistrement .. ENREGISTRE (le micro est actif !)\n"
            "   • forme d'onde ............... transcrit\n"
            "   • presse-papiers ............. écrit le texte\n"
            "Quand l'icône est sur « enregistre », le micro tourne : ne l'oublie pas.\n"
            "Sur un MacBook, l'icône peut se cacher derrière l'encoche de la caméra :\n"
            "réduis le nombre d'icônes voisines si tu ne la vois pas.\n"
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
            "  Passer à un modèle pas encore téléchargé demande internet UNE fois.\n"
            f"• Langue : Français / Anglais. Actuel : {lang}.\n"
            f"• Touche de dictée : Option droite (défaut), Cmd droite, Ctrl droite, F5.\n"
            f"  Actuel : {hk}. Le changement est immédiat (pas besoin de redémarrer).\n"
            f"• Réunions › Horodatage des passages : ajoute [mm:ss]. Actuel : {ts_state}.\n"
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
            "━━━ 8. HORS-LIGNE & VIE PRIVÉE ━━━\n"
            "\n"
            "Après l'installation, tout fonctionne SANS internet : ta voix ne quitte\n"
            "jamais ton Mac. Aucun compte, aucun abonnement, aucune clé.\n"
            "\n"
            "Journal technique (en cas de souci) :\n"
            "   ~/Library/Application Support/VoixFlash/voixflash.log"
        )

        try:
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

    def show_path(self, _sender):
        # On affiche le chemin STABLE du lanceur (celui que launchd utilise), pas le
        # realpath profond sous ~/.local/share/uv qui change à chaque mise à jour de uv.
        # Dans la liste de macOS, l'entrée apparaît sous le nom « Python ».
        rumps.alert(
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
        rumps.alert(
            title="Bienvenue dans VoixFlash 🎙️",
            message="Avant la première utilisation, autorise 3 choses dans les réglages "
                    "du Mac (menu « Aide & autorisations ») :\n\n"
                    "1) Microphone — pour entendre ta voix\n"
                    "2) Accessibilité — pour coller le texte (Cmd+V)\n"
                    "3) Surveillance des entrées — pour la touche de dictée\n\n"
                    "Ensuite, clique « Redémarrer VoixFlash ».\n\n"
                    f"Dictée éclair : maintiens la touche « {self._hotkey_label(self.config['hotkey'])} », parle, relâche.",
            ok="J'ai compris",
        )

    # --------------------------------------------------------------- divers --
    def restart_app(self, _sender):
        """Relance l'application (utile après avoir accordé des autorisations)."""
        if self._recording:
            try:
                ok = rumps.alert(
                    title="Enregistrement en cours",
                    message="Un enregistrement est en cours et sera perdu si tu redémarres "
                            "maintenant. Continuer ?",
                    ok="Redémarrer quand même", cancel="Annuler",
                )
            except Exception:
                ok = 1
            if not ok:
                return
            try:
                self._stop_recording()      # libère proprement le micro
            except Exception:
                pass
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
