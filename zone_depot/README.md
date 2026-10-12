# Zone de dépôt des fichiers d'enquête

Avant de lancer le nettoyage, placez dans ce dossier les fichiers correspondant à la même version du questionnaire :

- l'export brut Kobo au format CSV;
- le questionnaire XLSForm au format `.xlsx`, avec l'onglet `survey`;
- facultatif : le catalogue des choix `code_choix.csv`. Si vous ne le fournissez pas, le script lit les choix dans l'onglet `choices` du XLSForm.

Pour utiliser l'onglet intégré, il doit contenir les colonnes `list_name`, `name` et `label` (ou `label::langue`). Lancez ensuite `src/partie1_pipeline_nettoyage.py`. Les fenêtres de sélection s'ouvriront dans ce dossier. Dans la fenêtre du catalogue facultatif, cliquez sur **Annuler** si les choix sont déjà dans le XLSForm. Vérifiez que les fichiers sélectionnés correspondent bien à l'enquête à traiter.

Ce dossier sert au dépôt local temporaire des fichiers à traiter. Les fichiers que vous y déposez sont exclus de Git afin d'éviter de publier des réponses d'enquête réelles par erreur; seule cette notice est versionnée. Les fichiers nettoyés et les rapports sont produits dans `outputs/`.
