# VoixFlash 🎙️ — Dictée vocale gratuite et hors-ligne pour Mac

Parle au lieu de taper. Une touche pour dicter partout, un bouton pour les réunions.
100 % gratuit, 100 % hors-ligne (moteur **faster-whisper**), aucune connexion ni
compte requis. Discret dans la barre des menus, quasi invisible au repos.

> Un **mode d'emploi complet** est intégré à l'app : icône VoixFlash ›
> **Aide & autorisations › Mode d'emploi complet**.

---

## 1. Installation (un seul fichier)

1. Garde les deux fichiers **dans le même dossier** : `install.command` et `voixflash.py`.
2. **Double-clique sur `install.command`.**
   - S'il refuse de s'ouvrir (« développeur non identifié »), fais un **clic droit ›
     Ouvrir › Ouvrir**. Si macOS bloque encore : **Réglages Système › Confidentialité et
     sécurité**, tout en bas, **« Ouvrir quand même »**.
   - Une fenêtre Terminal s'ouvre et prépare tout automatiquement (Python isolé,
     bibliothèques, modèle, démarrage automatique). Laisse-la travailler quelques minutes.
3. À la fin, l'icône **micro** (en blanc) apparaît en haut à droite, dans la barre des menus.

> L'installation a besoin d'internet **une seule fois** (pour télécharger le modèle).
> Ensuite, tout fonctionne hors-ligne.

---

## 2. Autoriser le micro et le clavier (obligatoire, à faire une fois)

macOS protège le micro et le clavier. Il faut autoriser VoixFlash **3 fois**.
Le plus simple : clique sur l'icône VoixFlash dans la barre des menus ›
**« Aide & autorisations »**, puis suis les boutons.

### Étapes détaillées

1. Clique l'icône VoixFlash › **Aide & autorisations › Ouvrir réglages › Microphone**.
   Active l'interrupteur (l'entrée s'appelle **« Python »**).
2. Reviens au menu › **Ouvrir réglages › Accessibilité**. Active l'interrupteur.
   *(C'est ce qui autorise le collage du texte avec Cmd+V.)*
3. Reviens au menu › **Ouvrir réglages › Surveillance des entrées**. Active l'interrupteur.
   *(C'est ce qui autorise la touche de dictée.)*
4. Clique l'icône VoixFlash › **« Redémarrer VoixFlash »** pour que tout soit pris en compte.

> Astuce : si tu ne vois pas l'entrée dans une liste, clique sur **+** et ajoute le programme
> dont le chemin est affiché par « Aide & autorisations › Voir le chemin à autoriser ».
> La première fois, macOS peut aussi afficher tout seul la demande de Microphone : clique **Autoriser**.

---

## 3. Utilisation

### Dictée éclair (partout)
1. Place le curseur dans n'importe quel champ de texte (mail, navigateur, note…).
2. **Maintiens la touche de dictée** (par défaut **Option droite**). Un petit son confirme que
   le micro écoute : **attends-le pour parler**, c'est ce qui évite de perdre le premier mot.
3. Parle, puis **relâche**. Un second son marque la fin de la capture.
4. Le texte s'écrit tout seul à l'endroit du curseur.

> **Échap** pendant que tu parles annule la dictée : rien n'est écrit. Un simple effleurement
> de la touche ne dicte rien non plus.
> Si le texte ne s'est pas collé, icône › **« Recoller la dernière dictée »**.
> **Mains libres** (à activer dans *Touche de dictée*) : un appui bref verrouille la capture,
> tu parles sans rien tenir, un nouvel appui arrête. La mention « mains libres » s'affiche
> à côté de l'icône tant que ça tourne.

### Réunion / enregistrement long
1. Clique l'icône VoixFlash › **« Démarrer une réunion »**.
2. Parle aussi longtemps que tu veux (l'icône montre l'état « enregistre » : le micro tourne).
3. Clique **« Arrêter la réunion »**. Le texte complet s'affiche dans une fenêtre, où tu peux
   le lire, le modifier, le **Copier** ou le **Supprimer**.
4. Pour le garder en fichier : menu › **Réunions › « Exporter la dernière réunion »**
   → un fichier daté est créé dans `~/Documents/VoixFlash Transcriptions`.

> **Repères** : pendant une réunion, ta touche de dictée ne dicte pas — elle **pose un repère**
> sur l'instant courant, avec un petit son de confirmation. Tous les repères sont listés en
> tête de la transcription. **Réunions › « Poser un repère… »** permet d'y joindre un mot.

> En réunion, le presse-papiers n'est **pas** touché tout seul (copie via le bouton).
> En dictée éclair, ton presse-papiers est préservé (si du texte) puis remis en place.

### Importer un fichier audio (ou vidéo)
1. Menu › **Réunions › « Importer un fichier audio… »**, puis choisis ton fichier
   (mp3, m4a, wav, flac, ogg, aiff… ou une vidéo mp4/mov — seule la piste audio est lue).
2. VoixFlash le transcrit **comme une réunion** : le texte s'affiche dans une fenêtre et
   s'ajoute à l'historique. La **langue est détectée automatiquement**.
3. Ça tourne **en arrière-plan** : la progression s'affiche dans le menu
   (« Transcription du fichier… NN % »). Tu peux **annuler** à tout moment (l'item devient
   « Annuler la transcription en cours ») sans perdre le texte déjà obtenu.

> Tout se fait sur le processeur : compte ~15 min pour 1 h d'audio en qualité « small »
> (plus lent en « medium »). Les fichiers longs (**2 h et plus**) sont découpés tout seuls,
> donc la mémoire reste stable. La séparation des locuteurs peut aussi s'appliquer aux
> imports (**Réunions › Séparer aussi les fichiers importés**) : compte alors **un quart de
> la durée de l'audio en plus**. Fichiers protégés (DRM) refusés.

### Indicateur d'état (barre des menus)
L'icône (un micro blanc) change de **forme** : micro fin = chargement · micro plein = prêt ·
pastille d'enregistrement = enregistre · forme d'onde = transcrit · presse-papiers = écrit le texte.

### Historique
- Toutes les transcriptions (dictées, réunions **et imports de fichiers**) s'ajoutent au menu
  **« Historique récent »**, **groupées par jour** (Aujourd'hui, Hier, puis la date).
  **Clique une entrée** pour la rouvrir (lire, modifier, copier, supprimer, nommer les locuteurs).
- **Rechercher** : **Historique récent › 🔍 Rechercher…** — tape un ou plusieurs mots-clés
  (accents et majuscules ignorés) ; les correspondances apparaissent dans **« Résultats de
  recherche »**, cliquables.
- **Réunions › Exporter…** et **Exporter tout l'historique (.txt)** créent des fichiers datés.

---

## 4. Réglages (menu de l'icône)

- **Qualité / vitesse** : *Rapide (tiny)* → *Très précis (medium)*. Défaut : **Précis (small)**.
- **Langue** : **Français** (défaut), **Anglais**, ou **Automatique** (détecte la langue
  à chaque dictée — pratique pour alterner FR/EN).
- **Touche de dictée** : préréglages (Option droite par défaut…) ou **« Choisir ma touche… »**
  qui capte la touche que tu presses (fiable quel que soit le clavier).
- **Texte dicté › Ajouter un mot au vocabulaire…** : écris un nom propre, une marque ou un
  terme métier tel que tu veux le voir apparaître. Les variantes approchantes sont corrigées
  automatiquement, même quand le moteur découpe le mot (*voie flash* devient *VoixFlash*).
  C'est le réglage qui change le plus de choses au quotidien.
- **Texte dicté › Corriger une faute récurrente…** : remplacement exact, de la version fautive
  vers la bonne. Sert aussi de raccourci de saisie (une phrase courte qui devient une signature).
- **Texte dicté › Retirer les hésitations** : efface les « euh » et « hmm » (activé).
- **Réunions › Importer un fichier audio…** : transcrit un fichier audio/vidéo existant
  (langue auto, découpage automatique, progression, annulable).
- **Réunions › Horodatage des passages** : ajoute `[mm:ss]` en tête de chaque **paragraphe**
  (réunions et imports), et non devant chaque phrase.
- **Réunions › Exporter en markdown** : le fichier exporté porte un titre et une date.
- **Réunions › Séparer les locuteurs** : affiche « — Locuteur 1 : … », « — Locuteur 2 : … »
  dans tes réunions. La **1re activation** télécharge un petit module (~50 Mo, depuis GitHub,
  **sans compte ni clé**) ; ensuite tout est hors-ligne. **Réunions › Locuteurs attendus**
  est un **plafond**, jamais un minimum : il empêche de découper une voix en plusieurs, mais
  ne force jamais à en fusionner. Choisis **1** si tu étais seul (la séparation ne tourne
  alors pas du tout), sinon laisse **Automatique**. La séparation fonctionne bien sur des
  voix distinctes et se dégrade quand plusieurs parlent en même temps.
- **Nommer les locuteurs** : dans la fenêtre d'une transcription, bouton **« Nommer les
  locuteurs »** (ou **Réunions › « Nommer les locuteurs de la dernière réunion… »**).
  « Locuteur 3 » devient « Marie » partout. Donne le **même nom** à deux locuteurs pour les
  **fusionner** : c'est la réparation à faire quand une seule personne a été découpée en deux.
- **Texte dicté › Ajouter une espace après le texte collé** : évite que deux dictées
  enchaînées se collent bord à bord (désactivé).
- **Restaurer le presse-papiers après une dictée** : remet ton ancien presse-papiers (activé).

> Le **1er choix** d'une qualité télécharge le modèle une fois (jusqu'à ~1 min pour
> *medium*, ~1,5 Go ; un message le signale). L'icône micro se remplit quand c'est prêt.
> Ensuite, tout est hors-ligne.

---

## 5. Désinstallation

Double-clique sur **`uninstall.command`**. Cela arrête l'app, retire le démarrage
automatique et supprime ses fichiers. Tes transcriptions `.txt` déjà exportées sont
conservées dans `~/Documents/VoixFlash Transcriptions`.

---

## En cas de souci

- Rien ne s'écrit en dictée éclair → vérifie **Accessibilité** *et* **Surveillance des
  entrées**, puis **Redémarrer VoixFlash**.
- La touche ne répond plus alors qu'elle marchait → **Aide & autorisations › « La touche de
  dictée ne répond plus ? »**. Indice : si Option marche encore mais que F5 ne fait rien,
  c'est la **saisie sécurisée** de macOS (un champ mot de passe ouvert quelque part).
- Pas de son capté → vérifie **Microphone**. Si VoixFlash annonce que le micro n'a **rien**
  capté, c'est l'entrée elle-même : regarde **Réglages Système › Son**, et vérifie qu'aucune
  visio n'accapare le micro.
- L'icône est introuvable → sur un MacBook, elle peut se cacher derrière l'encoche.
- Pour demander de l'aide → **Aide & autorisations › « Copier les informations système »**
  prépare un bloc à coller dans ton message. Il ne contient **aucun texte dicté**.
- Journaux techniques : `~/Library/Application Support/VoixFlash/voixflash.log` et
  `diagnostic.log` (compteurs audio seulement, jamais ce que tu dictes, sur 7 jours).
