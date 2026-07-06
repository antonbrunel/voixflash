# Journal des versions — VoixFlash

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
