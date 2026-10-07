# Guide utilisateur - Application de gestion des enquêtes

Ce guide accompagne les agents M&E dans l'utilisation quotidienne de l'application locale Streamlit. L'interface graphique est le parcours recommandé; Swagger est réservé aux personnes qui connaissent les requêtes API.

## 1. Préparer et démarrer l'application

Les commandes suivantes sont à lancer depuis PowerShell, à la racine du projet (le dossier qui contient `src`, `data` et `outputs`). Deux méthodes sont proposées : exécuter avec l'environnement `.venv` du projet ou utiliser `uv`.

### Option A - avec l'environnement `.venv`

1. Dans le premier terminal, saisir la clé fournie par le responsable. La saisie est masquée :

   ```powershell
   $secureApiKey = Read-Host "Clé API" -AsSecureString
   $env:M_E_API_KEY = [System.Net.NetworkCredential]::new("", $secureApiKey).Password
   ```

2. Dans ce même terminal, démarrer l'API :

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn src.api:app --reload
   ```

3. Ouvrir un deuxième terminal dans le même dossier, saisir de nouveau la clé avec les deux commandes ci-dessus, puis démarrer l'interface :

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run src\app.py
   ```

### Option B - avec `uv`

Cette option lance les services avec les dépendances indiquées dans `requirements.txt`. `uv` doit être installé et accessible depuis PowerShell (`uv --version` permet de le vérifier).

1. Dans le premier terminal, saisir la clé de la même façon :

   ```powershell
   $secureApiKey = Read-Host "Clé API" -AsSecureString
   $env:M_E_API_KEY = [System.Net.NetworkCredential]::new("", $secureApiKey).Password
   ```

2. Dans ce terminal, démarrer l'API :

   ```powershell
   uv run --with-requirements requirements.txt -- python -m uvicorn src.api:app --reload
   ```

3. Ouvrir un deuxième terminal dans le même dossier, saisir à nouveau la clé avec les deux commandes ci-dessus, puis démarrer l'interface :

   ```powershell
   uv run --with-requirements requirements.txt -- streamlit run src\app.py
   ```

Si `uv` affiche une erreur de commande introuvable, utiliser l'option A ou demander au responsable informatique d'installer/configurer `uv`. La première exécution avec `uv` peut prendre plus de temps, car il prépare l'environnement et vérifie les dépendances.

### Après le démarrage

Pour les deux options :

1. Garder les deux terminaux ouverts. L'API est prête lorsqu'elle écoute sur `http://127.0.0.1:8000`; Streamlit affiche l'adresse de l'interface, habituellement `http://localhost:8501`.
2. Ouvrir l'adresse affichée par Streamlit.
3. Dans le panneau latéral, laisser l'URL `http://127.0.0.1:8000` si l'API tourne sur le même poste, puis saisir la même clé API dans le champ masqué.
4. Pour arrêter proprement chaque serveur, revenir à son terminal et appuyer sur `Ctrl+C`.

### Information de sécurité sur la clé API

La clé n'est pas enregistrée dans le code. Elle est fournie aux deux processus par la variable d'environnement `M_E_API_KEY`, qui doit contenir la même valeur dans chacun des deux terminaux. La clé est saisie de manière masquée au démarrage; la variable ne reste définie que dans le terminal courant.

- Ne pas partager le dépôt, les captures d'écran ou les fichiers contenant la clé avec des personnes non autorisées.
- Ne pas exposer l'API ou Streamlit sur Internet ni les lancer avec une adresse d'écoute publique sans configuration par un responsable technique.
- Si la clé n'est pas définie, l'application Streamlit s'arrête avec un message explicatif et l'API refuse les requêtes. Demander la clé au responsable de l'outil; ne pas en inventer une.
- Fermer les terminaux à la fin de la session pour effacer leur variable d'environnement.

## 2. Choisir une fonction dans le menu

### Consulter la liste

1. Ouvrir **Lister les enquêtes (CSV propre)**.
2. Choisir le nombre de lignes à afficher puis cliquer sur **Charger les données propres**.
3. La liste provient du CSV propre s'il existe; sinon l'API utilise la table `META_ENQUETE`. La liste est ordonnée par identifiant, mais cette page n'affiche qu'un nombre limité de lignes.

### Consulter un ménage

1. Ouvrir **Consulter par Code Jeton**.
2. Saisir le jeton et lancer la recherche.
3. Lire les rubriques affichées. Les passages sans consentement sont enregistrés à des fins de suivi, mais leurs informations thématiques ne sont pas présentes dans les tables détaillées.

### Ajouter un nouvel export Kobo

Utiliser ce parcours uniquement pour un **export brut Kobo** au format CSV ou XLSX, avec les noms techniques de colonnes du questionnaire actuel.

1. Ouvrir **Importer / Ajouter des enquêtes**, puis choisir **Nouvel export Kobo**.
2. Sélectionner le fichier brut (CSV ou XLSX).
3. Cliquer sur **Nettoyer et intégrer le nouvel export** et attendre le message de confirmation.

L'application charge le questionnaire et le catalogue de choix XLSForm actuels, utilise automatiquement `volont` comme colonne de consentement et n'applique pas de bornes calendaires. Elle attribue des identifiants `MENAGE_n` séquentiels, insère les passages dans SQLite et ajoute les lignes au CSV propre.

Le nettoyage peut neutraliser une réponse vide ou incohérente, une valeur hors des choix/règles du formulaire, une sentinelle numérique ou des réponses après un refus de consentement. Le message de résultat distingue les passages traités des ménages consentants et donne les nombres insérés par table. Si aucun consentement n'est reconnu, les tables détaillées restent vides pour ces lignes; vérifier alors la colonne `volont` du fichier source avant de recommencer.

Un code jeton existant peut faire rejeter l'import pour éviter une double insertion. Si les données proviennent du cache, ne pas les envoyer comme un export Kobo : utiliser le parcours de réhabilitation ci-dessous.

### Réhabiliter un ménage supprimé

1. Choisir **Réhabiliter une enquête supprimée**.
2. Sélectionner l'archive souhaitée; l'écran indique l'ID du ménage et, si disponible, son code jeton.
3. Cocher la confirmation puis cliquer sur **Réhabiliter l'enquête**.
4. Vérifier la confirmation et le message indiquant si l'archive a été retirée du cache.

Cette archive est une copie déjà nettoyée des données SQL. Elle est restaurée directement dans SQL et à sa place numérique dans le CSV; le pipeline n'est pas relancé. Une archive reste dans le cache si sa suppression échoue; le message Streamlit le signale.

### Modifier une réponse

1. Ouvrir **Modifier une enquête (Non technique)**.
2. Saisir le code jeton ou l'ID technique `MENAGE_n`.
3. Choisir le champ dans la liste; son type et ses choix proviennent du questionnaire XLSForm original.
4. Saisir la nouvelle valeur, cocher la confirmation puis cliquer sur **Valider et appliquer la modification**.

La modification est écrite dans la table SQL correspondante et synchronisée dans le CSV propre. Les recommandations du nettoyage ne changent pas les types affichés ici. Si un jeton correspond à plusieurs ménages, utiliser l'identifiant technique quand il est demandé.

### Supprimer un ménage

1. Ouvrir **Supprimer un ménage**.
2. Saisir un code jeton ou un identifiant `MENAGE_n`, puis confirmer explicitement l'action.
3. Un indicateur **Suppression en cours** reste visible pendant l'archivage, le retrait des tables SQL et la mise à jour du CSV. Attendre le résultat avant de relancer l'action.
4. En cas de succès, vérifier la confirmation, le chemin de l'archive CSV et le nombre de ménages restants.

L'archive utilise un nom court tel que `cache/suppressions/menage_1.csv`. Les données liées du ménage sont supprimées de la base et du CSV propre. La réhabilitation ultérieure remet la ligne à sa place numérique et retire l'archive du cache.

Si un jeton correspond à plusieurs lignes, la suppression est refusée et l'interface affiche les identifiants techniques correspondants. Choisir le bon `MENAGE_n` avant de réessayer; ne pas supprimer par jeton si l'identité du ménage n'est pas certaine.

## 3. Rapport d'exécution

Les ajouts, suppressions, réhabilitations et modifications sont journalisés dans `outputs/rapport_execution_m_e.md`. Ces opérations actualisent le nombre de passages enregistré et le nombre de non-consentants du dernier bilan, sans lancer une nouvelle synthèse complète du pipeline. Un lancement manuel du nettoyage complet, lui, ajoute un nouveau bloc de synthèse.

Les rapports et CSV sont des fichiers du poste local. Avant une opération de masse ou une correction manuelle, demander une sauvegarde au responsable des données.

## 4. Swagger (utilisateurs techniques)

Quand l'API est démarrée, ouvrir `http://127.0.0.1:8000/docs`. Dérouler la route voulue, cliquer sur **Try it out**, renseigner le paramètre `x-api-key` lorsqu'il est demandé, puis cliquer sur **Execute**. Swagger sert à tester une route; pour les opérations courantes, préférer Streamlit afin de bénéficier des confirmations et des messages adaptés aux agents.

Routes principales :

| Besoin | Route |
|---|---|
| Lister les enquêtes | `GET /enquetes` |
| Consulter le profil | `GET /menages/jeton/{code_jeton}/profil` |
| Importer un export brut | `POST /enquetes/importer-fichier` |
| Supprimer un ménage | `DELETE /enquetes/supprimer/{identifiant}` |
| Lister les archives | `GET /enquetes/archives-suppressions` |
| Restaurer une archive | `POST /enquetes/restaurer-archive` |
| Modifier un champ | `PUT /enquetes/modifier-champ/{code_jeton}` |

L'ajout par import de fichier est la route prévue pour un export Kobo; il n'y a pas de route de saisie manuelle `POST /enquetes/ajouter` dans cette version.

## 5. Dépannage

| Symptôme | Que faire |
|---|---|
| L'interface indique qu'elle ne peut pas joindre le serveur | Vérifier que le terminal API est toujours ouvert et affiche le serveur actif; contrôler l'URL dans la barre latérale. |
| Clé refusée | Vérifier la clé auprès du responsable de l'outil. Ne pas la publier dans un document partagé ou une capture d'écran. |
| Import refusé parce que le jeton existe | Vérifier si c'est un doublon réel ou une enquête précédemment supprimée; pour cette dernière, restaurer l'archive au lieu de relancer un export. |
| La suppression semble longue | Attendre l'indicateur de progression et le résultat final. Ne pas cliquer plusieurs fois; contacter le support si l'indicateur se termine par une erreur. |
| Un jeton désigne plusieurs ménages | Se servir de la liste des identifiants `MENAGE_n` affichés et confirmer le ménage voulu. |
| Une réponse devient vide après import | Comparer cette réponse au CSV brut, au type et aux choix XLSForm, au consentement et aux règles `relevant`/`constraint`; le pipeline peut volontairement la neutraliser. |
| La restauration indique que le ménage existe déjà | Ne pas supprimer l'archive manuellement; demander au support de vérifier la base avant toute action. |
| Une route retourne une erreur 500 | Noter l'heure, le nom du fichier et le message affiché, puis transmettre ces informations au support avec la sortie du terminal API. Ne pas envoyer de données personnelles par messagerie non sécurisée. |

## 6. Précautions

- Ne jamais supprimer ou modifier directement un ménage dans SQLite ou dans le CSV pendant que l'API fonctionne.
- Ne pas modifier les noms techniques des colonnes ni les fichiers d'archive.
- Ne pas réimporter une archive de suppression par le parcours « Nouvel export Kobo » : ses réponses sont déjà normalisées.
- Ne pas arrêter l'API pendant une suppression, un import ou une réhabilitation.
- Les opérations sont locales et les données peuvent être sensibles; appliquer les règles de confidentialité de l'organisation.
