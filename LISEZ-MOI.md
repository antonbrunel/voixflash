# VoixFlash : dictée vocale gratuite et hors-ligne pour Mac

Parle au lieu de taper. Une touche pour dicter partout, un bouton pour les réunions.
Gratuit, sans compte, sans abonnement. Ta voix ne quitte jamais ton Mac.

> Un mode d'emploi plus détaillé est dans l'app : icône VoixFlash ›
> **Aide & autorisations › Mode d'emploi complet**.

---

## 1. Installation

1. Garde `install.command` et `voixflash.py` **dans le même dossier**.
2. **Double-clique sur `install.command`.** Une fenêtre noire s'ouvre et prépare tout
   toute seule. Laisse-la travailler quelques minutes.
3. L'icône **micro** apparaît en haut à droite, dans la barre des menus. C'est prêt.

> S'il refuse de s'ouvrir (« développeur non identifié ») : **clic droit › Ouvrir ›
> Ouvrir**. Si macOS bloque encore : **Réglages Système › Confidentialité et sécurité**,
> tout en bas, **« Ouvrir quand même »**.

> L'installation a besoin d'internet **une seule fois**. Ensuite, tout marche sans.

---

## 2. Autoriser le micro et le clavier

À faire une fois. Clique l'icône VoixFlash › **Aide & autorisations**, puis les
trois boutons, dans l'ordre :

1. **Ouvrir réglages › Microphone** : active l'interrupteur. *(Pour t'entendre.)*
2. **Ouvrir réglages › Accessibilité** : active l'interrupteur. *(Pour écrire le texte.)*
3. **Ouvrir réglages › Surveillance des entrées** : active l'interrupteur.
   *(Pour la touche de dictée.)*

Puis clique **« Redémarrer VoixFlash »**.

> Dans ces listes, VoixFlash apparaît sous le nom **« Python »**. C'est normal.

---

## 3. Utilisation

### Dictée éclair (partout)

1. Place le curseur où tu veux écrire (mail, navigateur, note…).
2. **Maintiens la touche de dictée** (par défaut **Option droite**). Un petit son te dit
   que le micro écoute : **attends-le pour parler**.
3. Parle, puis **relâche**. Un second son marque la fin.
4. Le texte s'écrit tout seul à l'endroit du curseur.

> **Échap** pendant que tu parles annule tout : rien n'est écrit. Effleurer la touche
> sans le vouloir ne dicte rien non plus.
>
> Si rien ne s'est écrit : icône › **« Recoller la dernière dictée »**.
>
> **Mains libres** (à activer dans *Touche de dictée*) : un appui court, et tu peux
> parler sans rien tenir. « mains libres » s'affiche à côté de l'icône. Un nouvel appui
> arrête.

### Réunion

1. Icône › **« Démarrer une réunion »**.
2. Parle aussi longtemps que tu veux.
3. Icône › **« Arrêter la réunion »**. Le texte s'affiche dans une fenêtre : tu peux le
   lire, le corriger, le copier ou le supprimer.
4. Pour le garder : icône › **Réunions › « Exporter la dernière réunion »**. Le fichier
   arrive dans **Documents › VoixFlash Transcriptions**.

> **Poser un repère** : pendant une réunion, ta touche de dictée marque l'instant où tu
> appuies, avec un petit son. Tous tes repères sont listés en haut du texte final, avec
> leur heure. Pratique pour retrouver un passage important dans une réunion d'une heure.
> **Réunions › « Poser un repère… »** permet d'y ajouter un mot.

> En réunion, VoixFlash ne touche jamais à ce que tu as copié. En dictée, ton
> presse-papiers est remis en place juste après.

### Transcrire un fichier existant

1. Icône › **Réunions › « Importer un fichier audio… »**, puis choisis ton fichier
   (mp3, m4a, wav… ou une vidéo, dont seul le son est lu).
2. VoixFlash le transcrit comme une réunion. La langue est reconnue toute seule.
3. Ça travaille en arrière-plan sans bloquer ton Mac. L'avancement s'affiche dans le
   menu, et tu peux **arrêter à tout moment** sans perdre ce qui est déjà écrit.

> Compte environ **15 minutes pour 1 heure d'enregistrement**. Les fichiers de 2 heures
> et plus passent sans souci. Les fichiers protégés contre la copie (Apple Music) sont
> refusés.

### L'icône dans la barre des menus

Micro fin = ça se prépare · micro plein = prêt · pastille rouge = **ça enregistre** ·
forme d'onde = ça transcrit · presse-papiers = ça écrit le texte.

### Historique

- Toutes tes transcriptions s'ajoutent à **« Historique récent »**, **classées par jour**
  (Aujourd'hui, Hier, puis la date). Clique une ligne pour la rouvrir.
- **Historique récent › 🔍 Rechercher…** : tape un mot, les résultats montrent le passage
  trouvé. Les accents et les majuscules n'ont pas d'importance.

---

## 4. Réglages (icône VoixFlash)

**Les plus utiles**

- **Texte dicté › Ajouter un mot au vocabulaire…** : écris un nom propre, une marque ou
  un mot de ton métier comme tu veux le voir. VoixFlash l'orthographiera correctement,
  même s'il l'entend en deux morceaux (*voie flash* devient *VoixFlash*). C'est le
  réglage qui change le plus de choses au quotidien.
- **Texte dicté › Corriger une faute récurrente…** : remplace un mot mal transcrit par le
  bon, à tous les coups. Sert aussi de raccourci : une phrase courte qui se transforme en
  un texte long (ta signature, ton adresse).
- **Qualité / vitesse** : de *Rapide* à *Très précis*. Par défaut *Précis*, un bon
  compromis.
- **Langue** : Français, Anglais, ou Automatique si tu alternes les deux.
- **Touche de dictée** : choisis parmi les propositions, ou **« Choisir ma touche… »** et
  appuie sur celle que tu veux.

**Réunions**

- **Séparer les locuteurs** : affiche « Locuteur 1 », « Locuteur 2 » dans tes réunions.
  La première activation télécharge un petit complément (environ 50 Mo), une seule fois.
- **Locuteurs attendus** : un **maximum**, pas un nombre exact. Il évite qu'une même
  personne soit comptée pour deux, mais ne force jamais à regrouper. Choisis **1** si tu
  étais seul. Dans le doute, laisse **Automatique**.
- **Nommer les locuteurs** : dans la fenêtre d'une réunion, bouton **« Nommer les
  locuteurs »**. « Locuteur 3 » devient « Marie » partout. Donne le **même nom à deux
  locuteurs pour les regrouper**, quand une seule personne a été comptée deux fois.
- **Séparer aussi les fichiers importés** : même chose sur un fichier que tu importes.
  Compte un quart d'heure de plus par heure d'enregistrement.
- **Horodatage des passages** : ajoute l'heure (03:12) au début de chaque paragraphe.
- **Exporter en markdown** : le fichier exporté porte un titre et une date.

**Confort**

- **Retour sonore** : les petits sons de début et de fin de dictée.
- **Restaurer le presse-papiers** : remet en place ce que tu avais copié (activé).
- **Ajouter une espace après le texte collé** : évite que deux dictées se collent l'une
  à l'autre (désactivé).

---

## 5. Désinstallation

Double-clique **`uninstall.command`**. Tout est retiré. Tes transcriptions déjà
exportées restent dans **Documents › VoixFlash Transcriptions**.

---

## En cas de souci

- **Rien ne s'écrit** : vérifie **Accessibilité** *et* **Surveillance des entrées**,
  puis **« Redémarrer VoixFlash »**.
- **La touche ne répond plus alors qu'elle marchait avant** : icône ›
  **Aide & autorisations › « La touche de dictée ne répond plus ? »**. VoixFlash te dit
  ce qui bloque et répare ce qu'il peut.
- **VoixFlash dit qu'il n'a rien entendu** : ce n'est pas toi, c'est le micro. Va dans
  **Réglages Système › Son** et vérifie qu'un appel vidéo ne l'occupe pas.
- **L'icône a disparu** : sur un MacBook, elle peut se cacher derrière l'encoche de la
  caméra. Réduis le nombre d'icônes voisines.
- **Pour demander de l'aide** : icône › **Aide & autorisations › « Copier les
  informations système »**. Colle le résultat dans ton message. Il ne contient rien de
  ce que tu as dicté.
