# VoixFlash — Compte rendu de session (16 juin 2026)

Document exhaustif de **toutes** les corrections, améliorations et décisions de cette
session. Rien n'est omis : chaque point est listé, même mineur.

Fichiers concernés : `voixflash.py` (application) et `install.command` (installeur).
Tout a été **déployé** dans la copie active `~/Library/Application Support/VoixFlash/`
et vérifié sur l'app en fonctionnement (relances via `launchctl kickstart -k`).

---

## 0. Vue d'ensemble

| Catégorie | Corrigés |
|---|---|
| Plantages / blocages bloquants | 3 |
| Permissions & intégration macOS | 3 |
| Icône & barre des menus | 2 |
| Stabilité (threads / audio / process) | 5 |
| Refonte historique (SQLite) | 6 |
| Fenêtre de transcription | 4 |
| Menu & UX | 7 |
| Qualité de transcription | 1 |
| Installeur | 8 |
| **Total** | **~39 points** |

Deux **audits adversariaux multi-agents** ont été menés (20 puis 4 problèmes confirmés,
chacun re-vérifié par un second agent indépendant), plus une revue de non-régression.

---

## 1. Plantages & blocages (critiques)

### 1.1 Crash au lancement — `.clear()` sur un sous-menu non construit
- **Symptôme** : l'app mourait avant d'afficher son icône ; aucune icône dans la barre.
- **Cause** : `_refresh_quality_menu()` (et 3 autres) appelaient `self.<menu>.clear()` au tout
  premier build, alors que le `NSMenu` interne (`_menu`) valait encore `None` →
  `AttributeError: 'NoneType' object has no attribute 'removeAllItems'`.
- **Touchait 4 sous-menus** : Qualité, Langue, Touche de dictée, Historique.
- **Correctif** : helper `_safe_clear()` qui ne vide que si `getattr(menu, "_menu", None)` n'est
  pas `None`. (`.add()` recrée le menu paresseusement, donc il reste sûr.)
- **Observation liée** : le `LaunchAgent` (`KeepAlive`) relançait l'app crashée en boucle,
  d'où une session ralentie. Résolu de fait par le correctif du crash.

### 1.2 Chargement du modèle infini — appel réseau Hugging Face bloquant
- **Symptôme** : icône bloquée sur « chargement », « le moteur se charge encore » à l'appui touche.
- **Cause** : `faster-whisper` contactait Hugging Face pour *re-vérifier* le modèle **même
  déjà en cache** ; la connexion (route IPv6 vers le CDN HF) restait en `SYN_SENT`,
  aggravée par l'étranglement des requêtes anonymes (avertissement `HF_TOKEN`).
- **Diagnostic** : process bloqué en `SYN_SENT` vers le CDN HF ; chargement cache-only = 1,64 s.
- **Correctif** : `_load_model` charge d'abord `WhisperModel(..., local_files_only=True)`
  (zéro réseau), avec repli sur téléchargement **uniquement** si absent du cache. Hors-ligne par défaut.

### 1.3 Crash au changement de touche de dictée
- **Symptôme** : sélectionner une autre touche faisait planter l'app.
- **Cause** : le callback recréait l'écoute `pynput` (event tap Quartz) **depuis le thread
  principal Cocoa**, ce qui fait planter l'app.
- **Correctif** : on change `self._hotkey` « à chaud » (l'écoute capte déjà toutes les touches
  et les compare à la cible) — **aucun** redémarrage de listener. Callback enveloppé en
  `try/except`. Ajout de `_hotkey_label()`.

---

## 2. Permissions & intégration macOS

### 2.1 Microphone absent de Réglages › Confidentialité
- **Cause** : tant que l'app n'a jamais *demandé* le micro, macOS ne l'inscrit pas dans la
  liste → impossible à cocher.
- **Correctif** : `_prime_microphone()` ouvre brièvement l'entrée audio **une fois** (drapeau
  `mic_primed` en config) pour déclencher la demande TCC. Aussi déclenché (force) par le
  bouton « Aide & autorisations › Ouvrir réglages › Microphone ».

### 2.2 Redémarrage laissait un emplacement « fantôme »
- **Cause** : `os.execv` sur une app de barre des menus laisse la case réservée mais l'icône ne
  revient jamais (le serveur de fenêtres garde l'ancien `NSStatusItem`).
- **Correctif** : `_relaunch_via_launchd()` → `launchctl kickstart -k gui/<uid>/<label>`
  (processus neuf, icône neuve), repli sur `os.execv`. **Gardé** par
  `XPC_SERVICE_NAME == LAUNCHD_LABEL` pour ne pas créer une instance en double si l'app a été
  lancée manuellement (voir 4.x).

### 2.3 Chemin d'autorisation peu clair
- **Correctif** : `show_path` affiche le chemin **stable** du lanceur (`sys.executable`, celui
  utilisé par launchd) et non plus le `realpath` profond sous `~/.local/share/uv` (qui change à
  chaque mise à jour de `uv`) ; précise que l'entrée apparaît sous le nom « Python ».
  Méthode morte `_real_python` supprimée.

---

## 3. Icône & barre des menus

### 3.1 Icône d'état : emojis → symboles SF (template blanc)
- **Avant** : ⏳ / 🟢 / 🔴 / 🟠 / ✍️ (dénotaient dans la barre).
- **Après** : symboles SF rendus en « template » (blanc/noir comme les icônes natives). État par
  la **forme** du glyphe : `mic` (chargement) · `mic.fill` (prêt) · `record.circle`
  (enregistrement) · `waveform` (transcription) · `doc.on.clipboard` (collage).
- **Implémentation** : `_symbol_image()` (cache + `NSImageSymbolConfiguration`), `_apply_state_icon()`,
  table `STATE_SYMBOLS`. Repli sur les emojis (`STATE_TITLES`) si les symboles SF sont indisponibles.

### 3.2 Menu réunion sans emoji + libellé « une »
- « 🔴 Démarrer la réunion » → **« Démarrer une réunion »** ; « ⏹ Arrêter… » → **« Arrêter la réunion »**.
- Constantes `MEETING_START_TITLE` / `MEETING_STOP_TITLE` utilisées partout (menu, watchdog, bascule).

---

## 4. Stabilité (threads, audio, process)

### 4.1 Les fenêtres modales gelaient les garde-fous
- **Cause** : une fenêtre/alerte modale fige le thread principal, donc le minuteur d'UI ; les
  garde-fous (relance de l'écoute, arrêt auto d'un enregistrement emballé) en dépendaient.
- **Correctif** : `_watchdog_loop()` sur un **thread dédié** (réveil toutes les 2 s) qui survit
  aux modales. Le watchdog ne touche jamais l'UI directement : la remise du titre réunion passe
  par la file (`meeting_title`).

### 4.2 Concaténation audio lourde sur le thread principal
- **Cause** : l'arrêt auto d'une réunion de 3 h faisait `np.concatenate` (~330 Mo) sur le thread
  d'UI → gel de la barre.
- **Correctif** : conséquence directe de 4.1 — l'arrêt tourne maintenant sur le thread dédié.

### 4.3 Fuite d'un flux audio orphelin (repli 16 kHz)
- **Cause** : si le flux 16 kHz s'ouvrait mais que `.start()` échouait, un second flux était
  ouvert sans fermer le premier (micro « chaud » jamais relâché).
- **Correctif** : fermeture + remise à `None` du flux partiel avant d'ouvrir le repli.

### 4.4 `subprocess.run` sans délai maximal
- **Correctif** : wrapper `_run()` (`@staticmethod`) — `timeout` par défaut, aucune exception ne
  remonte. Tous les appels (`pbcopy`, `pbpaste`, `open`, `launchctl`) passent par lui.

### 4.5 Réunion vide sans aucun retour
- **Cause** : une réunion sans parole détectée se terminait en silence → impression de réunion perdue.
- **Correctif** : message explicite « aucun texte détecté » en mode réunion.

---

## 5. Refonte de l'historique (SQLite)

### 5.1 Stockage moderne et scalable
- Passage d'un `history.json` (liste plafonnée) à une **base SQLite** `history.db` (incluse dans
  Python, **zéro dépendance**). Avantages : monte en charge sur des années, ne charge jamais tout
  en mémoire, suppression ciblée, taille bornée.
- **Fonctions** : `history_init`, `history_add`, `history_recent`, `history_get`,
  `history_last_meeting`, `history_delete`, `history_all`, `history_clear`, contextmanager
  `_hist_db()` (connexion courte par opération, sûre depuis n'importe quel thread).
- **Purge auto** : conservation des `HISTORY_KEEP = 1000` plus récentes.

### 5.2 Migration `history.json` → SQLite (sans perte de données)
- Import automatique une seule fois, puis archivage de l'ancien fichier en `.bak`.
- **Durcissement** (audit) : on n'archive en `.bak` **que** si l'import a réussi (ou liste vide
  légitime). Si le fichier est **illisible/corrompu** ou si la base est **déjà peuplée**, on
  **conserve** le fichier et on journalise (aucune donnée perdue, réessai possible).
  Validé sur 4 cas : corrompu / base peuplée / normal / vide.

### 5.3 Entrées d'historique cliquables
- Chaque entrée récente (15 affichées) ouvre la **fenêtre de transcription** (`_make_history_cb`).
  Fini les libellés à emoji ; format « N. Réunion · aperçu… ».

### 5.4 Exporter tout l'historique
- `export_all_history` : fichier `.txt` **daté** (plus d'écrasement), dans le dossier de
  transcriptions, + accusé de réception.

### 5.5 Vider l'historique
- `clear_history` avec **confirmation** (« Tout vider »).

### 5.6 Supprimer une entrée
- Bouton **Supprimer** dans la fenêtre de transcription (avec confirmation), via `history_delete`.

---

## 6. Fenêtre de transcription (`_show_transcript`)

Utilisée pour **la fin de réunion** ET **le clic sur une entrée d'historique**.

### 6.1 N'écrase plus le presse-papiers
- L'ancienne fenêtre copiait le texte d'office. Désormais **aucune** copie à l'ouverture ; la
  copie est un geste **explicite**.

### 6.2 Texte modifiable + boutons
- Boutons, de droite à gauche : **Fermer · Copier · Enregistrer les modifications · Supprimer**.

### 6.3 Copier (prend en compte les modifications)
- Copie la version **affichée** (modifs comprises) + accusé « Copié ».

### 6.4 Enregistrer les modifications
- Si le texte a changé → **nouvelle entrée** d'historique ; sinon message « Aucune modification ».
- *Limite assumée* : `rumps`/`NSAlert` est modal (chaque bouton ferme la fenêtre) ; on ne peut
  pas griser le bouton en direct → on vérifie après coup. Choix volontaire (simple et robuste, pas
  de fenêtre Cocoa sur-mesure fragile).

---

## 7. Menu & UX

| Avant | Après |
|---|---|
| « Enregistrer la dernière réunion (.txt) » | **« Exporter la dernière réunion (.txt) »** (dans le sous-menu Réunions, via `history_last_meeting`) |
| « Ouvrir tout l'historique » (doc texte unique) | **« Exporter tout l'historique (.txt) »** daté + **« Vider l'historique… »** |
| « Horodatage des réunions » | **« Horodatage des passages »** (dans le sous-menu Réunions) |
| « Restaurer le presse-papiers » | **« Restaurer le presse-papiers après une dictée »** |
| Réglages éparpillés | Nouvel **onglet « Réunions »** (export + horodatage) |

Autres :
- **Welcome** affichait `alt_r` brut → libellé lisible via `_hotkey_label` (« Option droite »).
- **Changement de touche** : ne donnait **aucun** retour visible (les notifications macOS ne
  marchent pas hors bundle) → alerte de confirmation. Fonction `_notify` (invisible) **supprimée**.
- Helpers ajoutés : `_show_info` (info visible) et `_confirm` (confirmation).

---

## 8. Qualité de transcription

### 8.1 Garde-fou anti-hallucination (silence)
- **Cause** : sur du silence/bruit, Whisper invente des phrases parasites (« Sous-titres réalisés
  par la communauté d'Amara.org »…) qui étaient **collées dans le document**.
- **Correctif** : `is_probably_hallucination()` + `HALLUCINATION_MARKERS`, **conservateur** (n'écarte
  que des marqueurs jamais dictés en vrai, pour ne jamais supprimer de la vraie parole). Appliqué
  avant collage/enregistrement.

---

## 9. Installeur (`install.command`)

### 9.1 Téléchargement du modèle
- Message rassurant (« plusieurs minutes, c'est normal ») + **indicateur animé** (`spin`).
- Avertissement **`HF_TOKEN` masqué** (réaffiché seulement en cas d'échec, après filtrage).
- Pré-télécharge le **modèle réellement configuré** (lu dans `config.json`), pas « small » en dur.

### 9.2 Fin d'installation honnête
- **Vérification réelle du démarrage** : `state = running` + absence de `Traceback` récent dans le
  journal. En cas d'échec → affiche les 20 dernières lignes du journal et **sort en erreur** (au
  lieu d'« Installation terminée »).
- **Message honnête** si le modèle n'a pas pu être préparé (`DL_OK`).

### 9.3 Robustesse du script
- `set -o pipefail` (un échec de `curl … | sh` n'est plus masqué).
- **Piège `EXIT`** : tout arrêt anormal affiche un message clair en français + pause (`HANDLED`
  évite les doubles messages).
- Vérification explicite « `uv` manquant ».
- **Réutilisation du venv existant** s'il fonctionne → préserve les autorisations TCC (sinon une
  réinstallation cassait micro/clavier/collage silencieusement).

### 9.4 « Où est l'icône ? »
- Description de l'icône (micro blanc), piège de **l'encoche** (MacBook), chemin du **journal**,
  et quoi faire si elle n'apparaît pas.

---

## 10. Audits adversariaux (méthodologie & résultats)

### 10.1 Audit #1 — code global
- **20 confirmés / 7 rejetés.** Corrigés : gel des garde-fous sous modale (thread dédié), réunion
  vide sans retour, instance en double au redémarrage, libellé `alt_r`, fuite de flux audio,
  timeouts `subprocess`, chemin d'autorisation. Côté installeur : `pipefail` + piège, réutilisation
  du venv, message honnête modèle, pré-téléchargement du modèle configuré.
- **Revue de non-régression** des ~17 modifications : aucune régression.

### 10.2 Audit #2 — nouvelles fonctionnalités
- **4 confirmés / 2 rejetés.** Corrigés : retour invisible au changement de touche, durcissement de
  la migration (anti-perte), accusé « Copié », accusé + datage de l'export global.

---

## 11. Points écartés **volontairement** (avec justification)

- **Détection « Surveillance des entrées » refusée** : nécessiterait la bibliothèque `IOKit` (non
  embarquée) ; l'aide existe déjà dans 3 endroits du menu, et « Python » apparaît déjà dans cette liste.
- **Course d'écriture de `config.json`** entre threads : bénin (écriture atomique sur disque,
  affectation GIL-atomique), fenêtre de ~150 ms au tout premier lancement.
- **Micro débranché en pleine session** (USB/Bluetooth) : cas rare ; le correctif côté callback
  audio était jugé risqué (risque d'inter-blocage).
- **Fausse alerte « suppression sur Annuler »** (audit #2) : **vérifié dans la source de `rumps`**
  avant d'écarter — `rumps.alert` renvoie `1` pour OK et `0` pour Annuler ; les confirmations
  Supprimer/Vider sont donc **sûres**.

---

## 12. Récapitulatif technique

### Imports ajoutés
`sqlite3`, `contextlib`.

### Constantes / config ajoutées
`LAUNCHD_LABEL`, `HISTORY_DB`, `HISTORY_KEEP`, `MEETING_START_TITLE`, `MEETING_STOP_TITLE`,
`STATE_SYMBOLS`, `HALLUCINATION_MARKERS`, et la clé de config `mic_primed`.

### Éléments supprimés (nettoyage)
`self.history` (liste mémoire), `_last_meeting_text`, `_show_meeting`, `_make_copy_cb`,
`save_last_meeting`, `open_full_history`, `_real_python`, `_notify`.

### Fichiers générés au runtime
`history.db` (base SQLite), `history.json.bak` (sauvegarde de l'ancien format).

---

## 13. Vérifications effectuées

- Compilation (`py_compile`) et syntaxe shell (`bash -n`) à chaque étape.
- Couche historique SQLite testée de bout en bout (migration, ajout, lecture, suppression,
  purge, vidage, ré-init idempotente).
- Migration durcie testée sur 4 cas (corrompu / base peuplée / normal / vide).
- Filtre anti-hallucination testé (parasites écartés, vraie parole conservée).
- Logique de l'installeur testée en isolation (`spin` + `wait`, piège + `HANDLED`, `pipefail`).
- Valeurs de retour `rumps.alert` vérifiées dans la source (OK=1, Annuler=0).
- App relancée et observée stable après **chaque** déploiement (journal sans `Traceback`,
  modèle chargé depuis le cache, données intactes).

---

*Toutes les modifications sont déjà actives dans la copie installée. Une réinstallation
(`install.command`) n'est nécessaire que pour bénéficier des améliorations de l'installeur lui-même.*
