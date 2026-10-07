# Guide utilisateur - Nettoyage des enquêtes Kobo

Ce guide explique comment lancer le nettoyage complet d'un export Kobo, quels fichiers sélectionner et comment interpréter les résultats. Il s'adresse aux agents M&E qui exécutent la pipeline depuis le poste de travail.

## 1. Quel parcours utiliser ?

- **Nettoyer un export brut complet** : utiliser le script décrit dans cette notice.
- **Ajouter quelques nouvelles enquêtes à l'application** : utiliser Streamlit, parcours **Nouvel export Kobo**; voir [la notice de l'application](./notice_user_api.md).
- **Restaurer un ménage supprimé** : utiliser Streamlit, parcours **Réhabiliter une enquête supprimée**. Ne pas renvoyer l'archive au pipeline : elle contient déjà des données nettoyées.

Le script de cette notice produit un CSV propre pour l'ensemble du fichier sélectionné. Il ne s'agit pas d'un bouton d'ajout incrémental à la base SQL.

## 2. Fichiers nécessaires

Vérifier que l'on dispose de ces trois fichiers :

1. L'export Kobo brut en CSV, habituellement `data/enquete_vul_brute.csv`.
2. Le catalogue de choix en CSV, habituellement `data/code_choix.csv`.
3. Le classeur XLSForm `.xlsx` avec au minimum les onglets `survey` et `choices`, habituellement dans `data/`.

Les noms de colonnes du CSV brut doivent correspondre aux noms techniques de la feuille `survey`. Le classeur doit correspondre à la version du formulaire ayant servi à la collecte. Ne pas prendre un CSV d'archive de suppression ou le CSV propre de l'application pour un export brut Kobo.

Avant de lancer le script, fermer Excel si l'un des fichiers de sortie est ouvert et conserver une copie de sauvegarde des fichiers d'entrée.

## 3. Lancer la pipeline sous Windows

1. Ouvrir PowerShell dans le dossier principal du projet (celui qui contient `src`, `data` et `outputs`).
2. Lancer :

   ```powershell
   .\.venv\Scripts\python.exe .\src\pipeline_nettoyage.py
   ```

3. Une fenêtre demande successivement :
   - le CSV brut;
   - le CSV `code_choix.csv`;
   - le classeur questionnaire `.xlsx`.
4. Sélectionner le bon fichier dans chaque fenêtre et confirmer.
5. Revenir au terminal PowerShell. Pendant le nettoyage, le script pose des questions dans la console. Saisir une réponse puis appuyer sur **Entrée** à chaque demande :

   | Question affichée dans le terminal | Valeur à saisir pour le questionnaire actuel |
   |---|---|
   | Date du début des enquêtes | Date officielle de début au format `JJ-MM-AAAA`, par exemple `01-04-2025`. |
   | Date de fin des enquêtes | Date officielle de fin au format `JJ-MM-AAAA`, par exemple `30-04-2025`. |
   | Nom technique de la colonne servant pour l'identification unique | `code_jeton` |
   | Nom technique de la colonne de consentement | `volont` |

   Les dates servent au contrôle de cohérence des dates d'enquête; elles ne sont pas déduites des dates affichées par le fichier. Pour ignorer ce contrôle, appuyer sur **Entrée** sans saisir de valeur pour chacune des deux questions de date. Ne renseigner qu'une seule borne n'applique pas de contrôle.

   Saisir les noms techniques exactement comme dans l'en-tête du CSV, sans espaces ni libellé traduit. Pour un autre questionnaire, vérifier les noms dans la première ligne du CSV brut et dans la colonne `name` de la feuille `survey`; ne pas reprendre automatiquement `code_jeton` ou `volont` si les noms du formulaire ont changé.

6. Laisser le terminal ouvert jusqu'au message indiquant que le traitement est terminé. Ne pas fermer la fenêtre pendant que le script analyse les données.

Si la commande indique que Python ou `.venv` est introuvable, vérifier que PowerShell est ouvert à la racine du projet et demander au support de vérifier l'installation. Ne pas installer des paquets au hasard.

## 4. Fichiers produits

Après une exécution réussie, consulter :

- `outputs/donnees_nettoyees.csv` : données propres produites par cette exécution. Le fichier est remplacé à chaque nouveau lancement du script.
- `outputs/rapport_execution_m_e.md` : synthèse de l'exécution; le script ajoute un bloc pour chaque nettoyage complet.
- `outputs/edna_mode_capit.json` : données d'audit détaillées destinées au suivi technique.

Copier ou archiver le CSV propre avant de relancer la pipeline si l'on doit garder la version précédente.

## 5. Ce que fait le nettoyage

La pipeline normalise les noms de colonnes et les textes, conserve les variables reconnues dans le formulaire, analyse les dates et les valeurs numériques, compare les réponses aux choix XLSForm, examine les règles `constraint` et `relevant`, détecte les jetons répétés et vérifie le consentement.

- Les doublons strictement identiques peuvent être supprimés.
- Si plusieurs lignes ont le même code jeton mais des réponses différentes, la première conserve le jeton; les suivantes reçoivent un code de remplacement à 5 chiffres et l'ancien est indiqué dans `code_initial_renseigne`. Les codes générés peuvent différer si le nettoyage complet est relancé depuis le brut.
- Les valeurs vides, hors choix, incohérentes avec des règles `relevant`, négatives ou sentinelles (selon les contrôles configurés) peuvent devenir vides dans le CSV propre.
- Tous les passages restent dans `META_ENQUETE` lors de l'ingestion SQL. Les tables thématiques, elles, ne contiennent que les lignes avec consentement reconnu.

Un `None`/une cellule vide n'est donc pas systématiquement un défaut d'import : cela peut être une réponse vide à la source ou une correction explicite du pipeline. Pour diagnostiquer, vérifier d'abord la ligne brute, le type/choix XLSForm et le message d'audit de la colonne.

## 6. Lire le rapport

Le rapport donne le nombre de lignes brutes, le périmètre validé, les non-consentements, les corrections d'identifiants et les principaux contrôles. Le nombre de jetons « régénérés » correspond aux lignes modifiées pendant cette exécution, pas au nombre de jetons répétés qui restent dans le CSV propre.

Les identifiants créés par la pipeline peuvent changer lors d'un nouveau nettoyage. Utiliser le CSV propre d'une même exécution avec son rapport associé; ne pas mélanger un CSV d'une exécution et un rapport d'une autre.

## 7. Problèmes fréquents

| Symptôme | Vérification / action |
|---|---|
| La fenêtre de sélection ne s'ouvre pas | Vérifier qu'on a lancé `src/pipeline_nettoyage.py` avec la commande ci-dessus et que l'application n'est pas bloquée derrière une autre fenêtre. |
| `FileNotFoundError` ou feuille `survey` introuvable | Sélectionner le classeur XLSForm du bon formulaire et vérifier qu'il contient `survey` et `choices`. |
| Beaucoup de réponses deviennent vides | Comparer les codes bruts au catalogue `choices`; vérifier les conditions `relevant`, les sentinelles et le consentement. Les libellés traduits ne sont pas nécessairement les codes bruts attendus au nouveau nettoyage. |
| Le nettoyage s'arrête avec une erreur | Ne pas écraser les entrées; garder le traceback complet et transmettre au support le nom des fichiers sélectionnés et l'étape affichée. |
| Le CSV propre paraît ancien ou n'a pas changé | Vérifier l'heure de fin dans le terminal, le chemin de sortie `outputs/` et si le CSV était ouvert/verrouillé dans Excel. |

## 8. Limites importantes

La pipeline applique les règles programmées pour ce questionnaire; elle ne reproduit pas nécessairement l'intégralité du moteur Kobo. En cas de modification de formulaire, le dictionnaire et le catalogue doivent être mis à jour et validés avant de traiter les nouvelles données. Un contrôle humain reste nécessaire avant diffusion ou analyse.
