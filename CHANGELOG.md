# Journal des versions — VoixFlash

## 1.6.0 — des réunions lisibles, et un micro qui se signale quand il est mort

- **« Locuteurs attendus » veut enfin dire quelque chose.** Le nombre choisi était
  transmis tel quel au moteur de séparation, qui ne l'honorait pas : mesuré sur un
  enregistrement à quatre voix, demander 2 locuteurs en rendait **un seul**, et demander
  3 en rendait deux. Le réglage annoncé comme « plus fiable » écrasait donc des
  personnes réelles. Le nombre est maintenant un **plafond**, appliqué après coup en
  fondant les deux voix les plus proches l'une dans l'autre, jusqu'à tenir sous la
  limite. Demander « 2 au plus » rend bien 2 locuteurs. Un plafond plus large que ce qui
  a été détecté ne force plus rien du tout.
- **Ce plafond ne coûte presque rien.** Refaire tourner le moteur aurait ajouté une
  dizaine de minutes sur une réunion d'une heure (mesuré à 0,24 fois la durée de
  l'audio). On réutilise le passage déjà fait et on recalcule une empreinte par voix :
  80 ms par prise de parole, une quinzaine de secondes sur une heure.
- **« J'étais seul » ne lance plus la séparation du tout**, au lieu de fabriquer des
  interlocuteurs imaginaires.
- **Les réunions se lisent.** Un horodatage par PARAGRAPHE au lieu d'un toutes les trois
  secondes, les paragraphes étant ouverts par un blanc dans la parole ou par une phrase
  terminée. Un blanc de plus de 20 secondes est signalé explicitement. C'est la
  différence entre une transcription d'une heure consultable et illisible.
- **Les respirations ne coupent plus la parole.** Le moteur découpait une phrase en
  trois tours dès qu'on reprenait son souffle, et le texte se retrouvait haché par des
  « — Locuteur 2 : » à répétition alors que personne n'avait rendu la parole.
- **Un « oui » lancé pendant que l'autre parle** ne déclenche plus deux changements
  d'en-tête pour trois mots.
- **Micro muet : on le dit.** Une entrée audio peut délivrer un enregistrement
  techniquement parfait et strictement vide (canal muet d'une interface, périphérique
  virtuel créé par un appel en cours). Whisper en tirait une phrase inventée, sans
  qu'on comprenne d'où elle sortait. Un signal exactement nul est maintenant reconnu
  comme une panne de route audio et signalé comme telle. Le test porte sur des zéros
  parfaits, jamais sur un seuil de volume : se taire quelques secondes reste normal.
- **Deux canaux sont mélangés au lieu d'un seul repris.** Sur une interface audio, le
  micro n'est pas forcément sur le premier canal. Si l'ouverture à deux canaux échoue,
  on retombe sur l'ancien comportement, donc rien de ce qui marchait ne peut cesser de
  marcher.
- **Hallucinations françaises.** Les formules de fin de vidéo (« Merci d'avoir regardé
  cette vidéo », « Abonnez-vous ») sont écartées quand elles constituent la totalité du
  texte reconnu, et uniquement dans ce cas : « Abonnez-vous à la newsletter avant
  vendredi » reste une vraie dictée.
- **Dictée mains libres**, à activer dans « Touche de dictée ». Un appui bref verrouille
  la capture : on parle sans rien tenir, un nouvel appui arrête, Échap annule. La
  mention « mains libres » s'affiche à côté de l'icône tant que ça tourne, parce qu'un
  micro qui enregistre pendant que l'utilisateur ne tient rien doit se voir. Désactivé
  par défaut : sur une touche modificatrice, activer ce mode fait de chaque effleurement
  une dictée.
- **« Recoller la dernière dictée »** dans le menu. Un collage peut échouer sans le
  moindre message (champ qui refuse Cmd+V, application qui n'avait pas le focus). Le
  texte, lui, est toujours en base.
- **Espace après le texte collé**, en option, pour que deux dictées enchaînées ne se
  collent pas bord à bord.
- **Plus de refus quand on dicte juste après avoir changé de qualité.** La dictée
  démarre et attend le moteur, au lieu de répondre « le moteur se charge encore ».
- **Un seul moteur en mémoire à la fois.** Changer de qualité construisait le nouveau
  moteur avant de libérer l'ancien : les deux coexistaient le temps du chargement.
- **Repères posés en direct.** Pendant une réunion, la touche de dictée ne servait à
  rien : elle pose maintenant un repère sur l'instant courant, avec un son de
  confirmation. Tous les repères sont listés en tête de la transcription finale. Sans
  modèle de langue, c'est le seul moyen honnête de produire des chapitres : c'est
  l'humain qui sait ce qui compte. « Réunions › Poser un repère… » permet d'y joindre
  un mot.
- **Historique groupé par jour** (Aujourd'hui, Hier, puis la date), avec l'heure de
  chaque entrée. Une liste horodatée à la seconde ne se parcourt pas ; on cherche
  presque toujours « ce que j'ai dicté ce matin ».
- **Les résultats de recherche montrent le passage trouvé**, pas les premiers mots de
  l'entrée. On ne savait pas si un résultat était le bon avant de l'avoir ouvert.
- **Export en markdown**, en option : le fichier porte son titre et sa date, et
  l'export complet de l'historique est groupé par jour.
- **Les fichiers importés peuvent séparer les locuteurs**, ce qui n'était pas possible
  jusqu'ici. Le fichier reste traité par blocs pour ménager la mémoire, et les voix sont
  reconnues d'un bloc à l'autre par leur empreinte : « Locuteur 2 » désigne la même
  personne du début à la fin. Sans cette réconciliation, un fichier d'une heure aurait
  produit une trentaine de locuteurs pour trois personnes. À activer dans « Réunions »,
  et l'estimation de durée annoncée avant le lancement en tient compte.
- **Nommer les locuteurs.** « Locuteur 3 » devient « Marie », dans toute la
  transcription. Donner le MÊME nom à deux locuteurs les fusionne, et les blocs voisins
  qui se retrouvent attribués à la même personne sont recollés : c'est la réponse à une
  voix découpée en deux. Depuis la fenêtre d'une transcription, ou depuis « Réunions ›
  Nommer les locuteurs de la dernière réunion… » pour les longues réunions qui s'ouvrent
  dans TextEdit.
- **Journal de diagnostic audio**, dans un fichier à part. Il répond à une seule
  question : le micro a-t-il vraiment délivré du son, et quand. Chaque capture y laisse
  l'ouverture du périphérique, le délai du premier bloc réellement reçu, un battement
  toutes les 30 secondes pendant une réunion, et un résumé de fermeture avec le nombre
  de blocs reçus et le nombre de blocs strictement vides. Ce dernier chiffre est le seul
  qui distingue « personne n'a parlé » de « la route audio était morte ». Aucun texte
  dicté n'y figure, jamais, et rien n'y est écrit depuis le fil temps réel du micro.
  Fenêtre de sept jours.
- **« Aide & autorisations › Copier les informations système »** produit un bloc prêt à
  coller dans un message : version, macOS, matériel, entrées audio disponibles, réglages,
  état des autorisations et douze dernières lignes du journal audio. Sans texte dicté,
  sans vocabulaire, sans historique.

> Écarté après mesure : **libérer le moteur après une période d'inactivité**. Sur cette
> pile, le construire coûte environ 210 Mo et le libérer n'en rend que 32 au système,
> le reste étant retenu par l'allocateur puis réutilisé au chargement suivant (vérifié
> sur dix cycles). La fonction n'aurait donc pas rendu de mémoire au Mac, seulement
> ajouté une attente. Le rechargement, lui, est bien immédiat (0,11 s cache chaud) :
> c'est ce qui rend l'attente au changement de qualité indolore.

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
- **La touche de dictée survit à la veille.** macOS coupe l'écoute du clavier pendant que le
  Mac dort, sans tuer le mécanisme qui la porte : le garde-fou existant ne voyait donc rien,
  et la touche restait muette jusqu'au redémarrage de l'app. C'était le scénario « mon Mac a
  dormi cette nuit, ce matin la dictée ne marche plus ». L'écoute est maintenant réarmée au
  réveil, et jamais pendant un enregistrement en cours.
- **Nouveau diagnostic** dans « Aide & autorisations › La touche de dictée ne répond plus ? ».
  Il distingue les trois causes qui se ressemblent de l'extérieur : autorisation manquante,
  écoute arrêtée, et **saisie sécurisée** (un champ mot de passe ouvert quelque part suffit à
  ce que macOS cesse de transmettre les touches). Il réarme l'écoute au passage.

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
