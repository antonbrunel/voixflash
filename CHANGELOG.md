# Journal des versions — VoixFlash

## 1.3.0 — fiabilité

Correction des blocages qui obligeaient à forcer la fermeture, et fin de la perte
des enregistrements en cours.

- **Les fenêtres passent devant.** VoixFlash est une application « accessoire » : ses
  alertes s'ouvraient derrière la fenêtre active, invisibles, alors qu'elles bloquaient
  l'application jusqu'au clic. L'app paraissait gelée. Toute fenêtre passe désormais au
  premier plan.
- **L'indicateur continue de vivre.** Le minuteur d'interface ne battait plus dès qu'un
  menu était déroulé ou une fenêtre ouverte : l'icône se figeait et les messages
  s'empilaient. Il est maintenant inscrit dans tous les modes de la boucle d'événements.
- **L'arrêt d'une réunion ne fige plus l'interface.** La fermeture du micro et
  l'assemblage de l'audio (des centaines de mégaoctets pour une longue réunion) se font
  dans un thread de fond, sans tenir le verrou interne.
- **Les réunions ne sont plus perdues.** L'audio est écrit sur le disque pendant tout
  l'enregistrement. En cas de fermeture forcée, de plantage ou d'extinction, VoixFlash
  propose de le transcrire au démarrage suivant. « Quitter » et « Redémarrer » conservent
  également l'enregistrement en cours.
- **Progression et annulation des réunions.** La transcription affiche son avancement en
  pourcentage dans le menu et peut être interrompue en gardant ce qui est déjà reconnu
  (comme l'import de fichier). Un brouillon est écrit au fil de l'eau.
- **Longues transcriptions.** Au-delà de 4 000 caractères, le texte s'ouvre dans TextEdit
  plutôt que dans une fenêtre d'alerte, dont la mise en page figeait l'application.
- **Chargement du modèle borné.** Délais maximaux sur les appels réseau et vérification
  de la connexion avant tout téléchargement : plus de blocage indéfini sur « chargement ».
- **Journal détaillé** de chaque étape (enregistrement, transcription, durées), pour
  diagnostiquer un souci après coup.

## 1.2.0

- **Séparation des locuteurs (réunions)** — nouvelle option « Réunions › Séparer les locuteurs ».
  Affiche « — Locuteur 1 : … », « — Locuteur 2 : … » dans les réunions enregistrées en direct.
  Module optionnel installé d'un clic à la première activation (sherpa-onnx + 2 modèles ONNX,
  ~50 Mo, téléchargés depuis GitHub — **aucun compte HuggingFace, aucune clé**), 100 % local
  ensuite. Sous-menu « Locuteurs attendus » (Automatique ou nombre imposé, plus fiable).
  Ne concerne pas l'import de fichier (transcrit par blocs indépendants).
- **Recherche dans l'historique** — « Historique récent › 🔍 Rechercher… » : recherche
  plein-texte (SQLite FTS5), accents et casse ignorés, résultats cliquables dans un sous-menu.
  Repli automatique sur une recherche simple si FTS5 est indisponible.
- Guide intégré et documentation mis à jour.

## 1.1.0

- Touche de dictée personnalisable, langue automatique, retours au changement de modèle.

## 1.0.0

- Version initiale : dictée éclair (push-to-talk), mode réunion, import de fichier audio,
  historique, hors-ligne (faster-whisper CPU), Apple Silicon.
