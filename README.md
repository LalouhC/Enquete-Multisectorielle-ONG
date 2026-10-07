# ⚠️ PROJET EN COURS DE DÉVELOPPEMENT ⚠️ Enquête Multisectorielle - ONG : Mission Data & IA

## Problématique Métier
Comment identifier et prédire le niveau de vulnérabilité critique des ménages à partir de leurs caractéristiques socio-démographiques et de leurs conditions de vie pour optimiser le ciblage de l'aide humanitaire ?

*(Analyse prédictive des facteurs de vulnérabilité multisectorielle et optimisation de la collecte et du traitement des données.)*

Le dépôt rassemble les outils développés pour explorer, nettoyer et exploiter les données d'enquêtes multisectorielles. Le projet est encore en cours de développement : les traitements et l'application doivent être utilisés avec les fichiers et la version du questionnaire correspondant à la collecte.

## Suivi du Projet
* **Tableau Trello :** [Projet final ONG](https://trello.com/b/2b8Sp1E4/projetfinalong)

## Outils disponibles

* **Notebooks d'analyse** : exploration des données, préparation/nettoyage et analyses de vulnérabilité. Ils servent à comprendre les données et à documenter les travaux en cours.
* **Pipeline de nettoyage** : traite un export brut Kobo à partir du questionnaire XLSForm et du catalogue de choix. Elle contrôle et harmonise les données, puis produit un CSV nettoyé et des rapports d'exécution.
* **Ingestion SQL** : organise les enquêtes dans une base SQLite relationnelle de 11 tables, avec une table de suivi des passages et des tables thématiques. Elle permet de retrouver et d'analyser les ménages consentants sans confondre les refus de consentement avec des réponses manquantes.
* **API FastAPI et application Streamlit** : interface locale pour consulter les enquêtes, ajouter un nouvel export Kobo, restaurer une enquête supprimée, modifier des réponses ou supprimer un ménage. L'application met à jour la base et les fichiers de suivi associés.

Ces outils répondent à des besoins métier complémentaires : fiabiliser les données avant analyse, suivre les passages d'enquête, faciliter la correction des dossiers et préparer l'analyse des vulnérabilités pour éclairer le ciblage de l'aide.

## Démarrage rapide

Le dépôt ne contient pas les données d'enquête. Après avoir obtenu les fichiers autorisés et installé les dépendances listées dans `requirements.txt`, choisir le parcours adapté :

* Pour nettoyer un export brut complet, suivre le [guide de nettoyage Kobo](docs/notice_user_pipeline.md).
* Pour consulter ou gérer les enquêtes dans l'application, suivre le [guide de l'application locale](docs/notice_user_api.md). L'API et Streamlit se lancent dans deux terminaux distincts.
* Pour consulter directement les données dans SQLite, suivre le [guide de la base SQL](docs/notice_user_sql.md).

Avant tout traitement, vérifier que le questionnaire XLSForm correspond à l'export Kobo. L'application nécessite également la clé d'accès `M_E_API_KEY`, fournie par le responsable de l'outil ; ne jamais inscrire cette clé dans le dépôt.

## Structure du Projet
* `data/` : fichiers locaux d'entrée, notamment les exports bruts Kobo, les dictionnaires et le questionnaire XLSForm. Ce dossier est exclu du dépôt car il peut contenir des données sensibles.
* `notebooks/` : analyses exploratoires, nettoyage et travaux de modélisation.
* `src/` : scripts de nettoyage et d'ingestion SQL, API FastAPI et application Streamlit.
* `docs/` : notices d'utilisation et schéma relationnel des tables.
* `.streamlit/` : configuration de présentation de l'application Streamlit.
* `outputs/` : fichiers produits localement, notamment le CSV nettoyé, la base SQLite et les rapports. Ce dossier est exclu du dépôt.
* `requirements.txt` : dépendances Python du projet.

Les dossiers `data/` et `outputs/` ne sont pas publiés sur GitHub. Ils doivent être préparés localement selon les consignes des notices. Le fichier `.gitignore` est conservé dans le dépôt afin d'éviter l'ajout accidentel de données, de bases locales, de caches ou de secrets.