# Blocages de l'interface : diagnostic et correctifs (v1.3.0, 09/09/2026)

Symptôme rapporté : l'app se fige à l'enregistrement ou à une étape de traitement,
l'icône ne change plus, seule la fermeture forcée débloque, et l'enregistrement en
cours est perdu.

## Causes identifiées

| # | Cause | Où | Correctif |
|---|-------|-----|-----------|
| 1 | Alerte modale invisible : `NSAlert.runModal()` bloque le thread principal, et l'app étant « accessoire » (`NSApplicationActivationPolicyAccessory`) la fenêtre s'ouvre DERRIÈRE l'app active | tout `rumps.alert` / `rumps.Window` | `app_to_front()` avant chaque modale, via `_modal_alert()`, point de passage unique |
| 2 | `rumps.Timer` inscrit son NSTimer en `NSDefaultRunLoopMode` seul → `_drain_ui` cesse de battre dès qu'un menu est déroulé ou une fenêtre ouverte | `rumps.py:712` | `_install_timer_common_modes()` : même timer ajouté en `NSRunLoopCommonModes` |
| 2b | Effet de bord du correctif 2 : `_drain_ui` peut désormais s'exécuter pendant le suivi d'un menu, et reconstruire un `NSMenu` en cours de parcours peut planter | `_drain_ui` | `_runloop_is_idle()` + `_MENU_REBUILD_KINDS` : les messages qui reconstruisent un menu sont différés dans `self._deferred` |
| 3 | `_stop_recording` appelé depuis un callback de menu (thread principal) faisait `stream.stop()` (peut pendre si le périphérique audio a changé) et `np.concatenate` (centaines de Mo), le tout **sous le verrou** | `_stop_recording` | Découpé : `_stop_recording` bascule les drapeaux et rend la main ; `_finalize_recording` fait le travail lourd dans un thread |
| 4 | Transcription d'une réunion en un seul `model.transcribe()` opaque : ~15 min de silence pour 1 h d'audio, indiscernable d'un plantage | `_process_audio` | `_collect_meeting_segments()` parcourt le générateur, publie la progression, écrit un brouillon et respecte l'annulation |
| 5 | Résultat affiché dans un `NSTextField` sans défilement (`rumps.Window`) : mise en page très lente sur un long texte | `_show_transcript` | Au-delà de `LONG_TEXT_CHARS` (4 000), fichier `.txt` ouvert dans TextEdit (`_show_long_transcript`) |
| 6 | Audio de réunion uniquement en RAM → fermeture forcée = perte totale | `_audio_cb` | Écriture disque continue (PCM 16 bits mono) + reprise au démarrage |
| 7 | Repli réseau du chargement de modèle sans délai maximal | `_load_model` | `HF_HUB_DOWNLOAD_TIMEOUT` / `HF_HUB_ETAG_TIMEOUT` posés avant l'import de `faster_whisper`, + `internet_reachable()` avant tout téléchargement |
| 8 | Journal ne consignant que les chargements de modèle | `log()` | Étapes et durées journalisées (début/fin d'enregistrement, fermeture du flux, transcription, reprise) |
| 9 | Alertes modales affichées **sous** `self._lock` (blocage du thread principal verrou tenu) | `import_audio_file`, `_offer_recovery` | Lecture de l'état sous verrou, alerte affichée après |

## Filet de sécurité des réunions

- Dossier : `~/Library/Application Support/VoixFlash/reunions_interrompues/`
- Par réunion : `reunion_<horodatage>.raw` (PCM 16 bits mono brut) + `.json` (`sr`, `started`, `version`)
- Écriture par un thread dédié alimenté par une `queue` — jamais depuis le callback
  PortAudio, qui est un thread temps réel. `fsync` tous les ~1 Mo.
- Effacement à un SEUL endroit : après `history_add()` réussi (`_process_audio`).
  Une transcription vide, en erreur, ou un moteur indisponible conservent l'audio.
- Au démarrage, `find_interrupted_meetings()` → dialogue `_offer_recovery`
  (Transcrire maintenant / Plus tard / Supprimer, ce dernier avec confirmation).
  `_run_recovery` attend le chargement du modèle jusqu'à 180 s.

## Conventions à connaître

- `rumps.alert` construit une `NSAlert` par l'API historique : `runModal()` renvoie
  **1 = ok, 0 = cancel, -1 = other** (vérifié via les `tag()` des boutons sur macOS 25.4).
  `rumps.Window`, lui, renvoie 1, 2, 3… (`% 999` dans rumps) pour les boutons ajoutés
  par `add_button`. Ne pas confondre les deux.
- `AppHelper.callAfter` n'est distribué que dans le mode normal de la boucle : les
  modales lancées par `_present` s'ouvrent donc l'une après l'autre, jamais imbriquées,
  jamais pendant qu'un menu est déroulé. C'est voulu — ne pas « optimiser » ce point.
- Ordre des boutons de l'API historique : défaut, other, cancel. Un bouton destructeur
  placé en `other` se retrouve juste sous le bouton par défaut → confirmation obligatoire.

## Vérifications faites

- Écriture / relecture de la sauvegarde brute : 30 s d'audio, octets identiques.
- Détection d'une réunion interrompue, progression monotone, annulation à la 6e phrase,
  effacement de la sauvegarde après écriture en historique, drapeaux libérés.
- Bout en bout dans l'app réelle : réunion factice de 10 s (voix `say`) déposée sur le
  disque, redémarrage de l'agent → dialogue affiché **au-dessus de Safari** (capture),
  transcription en 1,1 s, entrée créée en historique, fichier `.raw` supprimé.

## Reste à faire (non traité)

- La transcription d'une réunion charge toujours tout l'audio en mémoire (nécessaire
  pour la diarisation). Un découpage par blocs comme l'import réduirait l'empreinte,
  au prix de la cohérence des identités de locuteurs.
- `model_is_cached()` s'est révélé désynchronisé du cache réel de Hugging Face
  (modèle `tiny` annoncé en cache puis absent). Sans conséquence depuis le correctif 7,
  mais l'avertissement « Téléchargement du modèle » peut apparaître à tort.
