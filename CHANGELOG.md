# Journal des versions — VoixFlash

## 1.5.0 — la dictée sait se faire comprendre

- **Retour sonore.** Un son quand la capture démarre, un autre quand elle s'arrête, un
  troisième quand une dictée est abandonnée. Le son de départ est joué **au premier son
  réellement capté**, pas au moment où l'on croit avoir ouvert le micro : c'est le seul
  instant où « tu peux parler » est vrai. Désactivable dans le menu. Aucun son n'est joué
  quand le micro est un casque Bluetooth, pour ne pas le faire basculer en mode téléphone.
- **La fin des phrases n'est plus coupée.** L'enregistrement continue deux dixièmes de
  seconde après le relâchement de la touche : le dernier mot est encore dans les tampons du
  système au moment où l'on relâche, et il était tranché.
- **Les appuis involontaires ne produisent plus rien.** Un effleurement de la touche de
  dictée (moins de 0,3 s) est jeté au lieu de transcrire du bruit. La règle ne s'applique
  qu'aux touches modificatrices comme Option : sur une touche ordinaire, on peut relâcher
  aussitôt et continuer à parler.
- **Échap annule la dictée en cours.** Rien n'est transcrit ni collé, et le micro est libéré
  par le même chemin qu'un arrêt normal.
- **Les raccourcis clavier redeviennent des raccourcis.** Avec Option comme touche de dictée,
  taper Option+A lançait une dictée parasite qui collait du bruit. L'arrivée d'une touche
  ordinaire pendant le maintien annule désormais la capture.
- **L'icône ne reste plus bloquée.** Si la libération du micro échouait pendant une
  annulation, l'indicateur restait figé sur « enregistrement » alors que l'app ne faisait
  plus rien.

> Mesuré sur cette machine : le micro délivre son premier son 94 ms après l'ouverture. La
> préparation du micro à l'avance, envisagée après l'étude des outils concurrents (qui
> mesuraient 500 à 660 ms), n'aurait fait gagner que 36 ms : elle a été écartée plutôt que
> d'allumer en permanence l'indicateur micro de macOS.

## 1.4.0 — vocabulaire et collage sûr

- **Vocabulaire personnalisé.** Nouveau menu « Texte dicté ». Tu y ajoutes les mots dont
  l'orthographe doit être respectée (noms propres, marques, jargon métier) : les variantes
  approchantes produites par la transcription sont ramenées dessus, y compris quand un mot
  est découpé en deux ou trois morceaux (« voie flash » devient « VoixFlash »). Tu peux
  aussi enregistrer des corrections exactes, qui servent également de raccourcis de saisie.
  Tout est local, sans intelligence artificielle supplémentaire et sans coût de calcul.
- **Hésitations retirées.** Les « euh », « hmm » et compagnie disparaissent du texte, avec
  la virgule qu'ils laissaient derrière eux. Désactivable dans le même menu. Les hésitations
  propres à l'anglais ne sont retirées que si la langue anglaise est certaine.
- **Bégaiements corrigés.** « Je je je pense » redevient « Je pense ». Deux répétitions sont
  conservées : « non non c'est bon » est une vraie tournure.
- **Meilleure ponctuation.** Une courte phrase d'amorce dans la langue choisie est fournie au
  moteur, qui poursuit dans le même registre et ponctue et accentue plus fidèlement.
- **Collage sûr.** Le presse-papiers était écrit puis collé après un délai fixe, sans vérifier
  que l'écriture avait pris : on pouvait coller son contenu précédent. La restauration écrasait
  par ailleurs ce que tu avais copié entre-temps, et une image ou un fichier copié était perdu
  sans retour possible. Désormais : toutes les données du presse-papiers sont conservées puis
  restituées à l'identique, la restauration n'a lieu que si rien d'autre n'est venu s'y mettre,
  et deux dictées enchaînées rendent bien le contenu d'origine.
- **Dictées absentes des gestionnaires de presse-papiers.** Raycast, Alfred, Maccy et consorts
  n'archivent plus le texte dicté.
- **Raccourci de collage plus fiable.** Le Cmd+V simulé ne peut plus se mélanger à la touche de
  dictée encore enfoncée.
- **Longues réunions.** Le pic de mémoire d'une réunion d'une heure passe d'environ 4,4 Go à
  1 Go : assemblage de l'audio au fil de l'eau et rééchantillonnage par tranches, à résultat
  identique. C'était la cause probable des arrêts brutaux sur les enregistrements longs.
- **Moins de locuteurs fantômes.** En mode automatique, une longue réunion était découpée en
  trop de locuteurs (une même voix éclatée en plusieurs personnes). Le regroupement des voix
  est maintenant plus tolérant à mesure que la réunion s'allonge. Par ailleurs, tout
  « locuteur » qui totalise moins d'une seconde de parole (un rire, une sonnerie) est écarté,
  les locuteurs sont numérotés dans l'ordre où on les entend pour la première fois, et un
  passage tombé entre deux prises de parole est rattaché à la plus proche au lieu d'afficher
  « Locuteur ? ».

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
