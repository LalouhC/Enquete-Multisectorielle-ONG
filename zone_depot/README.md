# Zone de dépôt des fichiers d'enquête

Avant de lancer le nettoyage, placez dans ce dossier les trois fichiers correspondant à la même version du questionnaire :

- l'export brut Kobo au format CSV;
- le catalogue des choix `code_choix.csv`;
- le questionnaire XLSForm au format `.xlsx`.

Lancez ensuite `src/pipeline_nettoyage.py`. Les fenêtres de sélection s'ouvriront dans ce dossier. Choisissez chaque fichier demandé et vérifiez qu'il correspond bien à l'enquête à traiter.

Ce dossier sert au dépôt local temporaire des fichiers à traiter. Les fichiers que vous y déposez sont exclus de Git afin d'éviter de publier des réponses d'enquête réelles par erreur; seule cette notice est versionnée. Les fichiers nettoyés et les rapports sont produits dans `outputs/`.
