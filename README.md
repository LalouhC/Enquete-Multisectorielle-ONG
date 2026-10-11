# Enquête multisectorielle — qualité des données, vulnérabilité et aide à la décision

![Échange lors d’une enquête de terrain](assets/photo-enquete-terrain.png)

> **Prototype bêta de fin de formation, conçu pour explorer une méthodologie concrète au service des ONG.** L'approche n'a pas encore été validée par les pairs et devra être améliorée avant tout usage opérationnel. L'outil aide les équipes à analyser les informations; il ne décide pas à leur place.

## Contexte et problématique métier

Les équipes de suivi-évaluation des ONG doivent exploiter des questionnaires et des exports produits avec <a href="https://www.kobotoolbox.org/"><img src="assets/kobotoolbox-logo.svg" alt="KoboToolbox" width="110" /></a>, repérer les erreurs qui fragilisent les données, comprendre les besoins des ménages et partager rapidement des résultats compréhensibles avec les équipes opérationnelles. Le projet vise à transformer les fichiers d'enquête en données nettoyées, en analyses utiles et en informations plus faciles à mobiliser pour la décision humanitaire.

Pour répondre à ce besoin, le projet s'articule autour de la question suivante :

**Comment identifier et prédire le niveau de vulnérabilité critique des ménages à partir de leurs caractéristiques socio-démographiques et de leurs conditions de vie pour optimiser le ciblage de l'aide humanitaire ?**

*Analyse prédictive des facteurs de vulnérabilité multisectorielle et optimisation de la collecte et du traitement des données.*

Concrètement, le projet vise à donner aux équipes les moyens de :

- préparer et nettoyer des exports Kobo de plusieurs milliers de lignes, puis comprendre les principales erreurs techniques et incohérences métier à corriger;
- examiner les vulnérabilités par secteur et selon les caractéristiques socio-démographiques des ménages, sans fusionner tous les secteurs en un score opaque;
- visualiser les indicateurs dans un tableau de bord interactif, pour repérer les groupes ou zones qui nécessitent une analyse plus approfondie;
- explorer si un modèle de machine learning peut classer les niveaux de vulnérabilité observés et aider à parcourir les résultats, tout en montrant ses limites et ses risques;
- consulter, importer et corriger les dossiers dans une interface protégée, puis capitaliser les constats utiles pour les prochaines collectes.

## Comprendre les données et les résultats

### D'où viennent les bases de test ?

Le questionnaire fictif a été conçu pour être déployé sur KoboToolbox, avec des règles de codage inspirées des formulaires Kobo, mais sans base de réponses préexistante. Une première base synthétique de **50 000 lignes**, peu réaliste, a été générée pour éprouver le nettoyage sur des erreurs techniques volontaires et vérifier le traitement d'un fichier volumineux.

Une seconde base synthétique a ensuite été construite en s'appuyant sur les résultats d'une enquête réelle menée auprès d'environ **3 000 ménages en 2021**, dans la province de l'Équateur, en République Démocratique du Congo. Elle reprend des proportions de cette enquête, menée dans un axe d'intervention et un contexte géographique précis.

Les scripts de génération ne sont pas inclus dans le dépôt. Les bases synthétiques de démonstration sont rangées dans `data_test/` et leurs résultats figés dans `outputs_demo/`, destinés à être partagés avec le projet. Ils ne sont pas les exports originaux de la collecte de 3 000 ménages.

### Comment interpréter les résultats ?

Les outils utilisent les mêmes étapes de nettoyage et d'analyse pour les deux jeux. Ce qui change, ce sont les profils présents dans les données et donc les constats produits : la seconde base représente, de manière synthétique, la situation d'environ 3 000 ménages interrogés en 2021 dans un contexte géographique et un axe d'intervention précis. Elle permet d'éprouver les outils dans ce contexte, mais pas de supposer que les résultats ou les classifications du futur modèle s'appliqueront tels quels à d'autres zones, périodes ou populations.

### Que signifie une cellule vide, et que vérifier sur un autre questionnaire ?

Une cellule vide n'est pas toujours une erreur. Une question conditionnelle peut ne pas avoir été posée parce que la réponse précédente ne remplissait pas sa condition (`relevant`) : la cellule vide est alors attendue. Si la question devait être posée mais que la réponse manque, il peut s'agir d'une non-réponse. Un refus de consentement est encore un autre cas; enfin, le nettoyage peut vider une réponse invalide ou incohérente. Le rapport aide à repérer certains cas, mais il faut consulter la réponse brute, les conditions du questionnaire et le contexte avant de traiter une valeur absente.

Le nettoyage a été testé sur un questionnaire XLSForm simplifié : **toutes les règles Kobo ne sont pas intégrées**. Pour employer un autre questionnaire, une personne qui connaît la collecte doit vérifier les conditions `relevant`, les contraintes `constraint`, les questions requises `required`, le dictionnaire, les choix et les calculs.

Les indicateurs sont calculés séparément par secteur, avec leurs définitions et seuils documentés. Certains choix s'inspirent du JIAF et d'autres cadres humanitaires, mais le prototype ne constitue pas une application complète de ces méthodes. La base synthétique inspirée de la collecte de 2021 représente une situation donnée à un instant T, dans une zone et un axe d'intervention précis. Elle peut aider à éprouver les outils dans ce contexte, mais les résultats et les classifications du futur modèle ne sont pas automatiquement transposables à d'autres zones, périodes ou populations.

Les bases de démonstration sont synthétiques et destinées à rendre le projet testable. Avant de publier ou de remplacer ces fichiers par d'autres données, vérifier leur provenance et les autorisations; ne pas ajouter au dépôt les enregistrements originaux de l'enquête réelle.

### Où déposer les fichiers à nettoyer ?

Après avoir téléchargé le projet, les jeux synthétiques se trouvent dans `data_test/` et leurs résultats de référence dans `outputs_demo/`. Pour nettoyer un export, préparer dans `zone_depot/` les trois fichiers correspondant à la même enquête :

```text
projet/
├── data_test/                         # Jeux d'entrée synthétiques fournis
├── outputs_demo/                      # Résultats de démonstration publiés
├── zone_depot/                        # Dépôt local des fichiers à nettoyer
│   ├── enquete_vul_brute.csv          # Export brut Kobo
│   ├── code_choix.csv                 # Catalogue des choix
│   └── Questionnaire Vulnérabilités Fictif.xlsx
└── outputs/                           # Espace local de travail, ignoré par Git
```

Pour essayer le nettoyage sur l'exemple, copier depuis `data_test/` un seul CSV brut avec `code_choix.csv` et le questionnaire XLSForm correspondant, puis déposer ces trois fichiers dans `zone_depot/`. Pour une nouvelle collecte, déposer à cet endroit l'export brut, son catalogue de choix et le questionnaire XLSForm correspondant. Au lancement, les fenêtres de sélection du script s'ouvrent dans `zone_depot/`; choisir le fichier demandé à chaque étape. La [notice de la zone de dépôt](zone_depot/README.md) rappelle les fichiers à préparer.

Pour ouvrir l'application avec la base de démonstration, créer `outputs/` à la racine et y copier `outputs_demo/enquete_ms.db` et `outputs_demo/donnees_nettoyees.csv`. Pour traiter une nouvelle enquête, le script écrit les résultats dans `outputs/`, espace de travail local ignoré par Git; le CSV nettoyé est remplacé et les rapports sont mis à jour. Ainsi, les sorties de données réelles ne sont pas confondues avec les résultats de démonstration publiés.

Les fichiers déposés dans `zone_depot/` sont également ignorés par Git; seule la notice du dossier est versionnée. Cette protection évite l'ajout accidentel de nouvelles données de collecte réelles.

## Comment utiliser le projet ?

### Parcours pour un·e agent·e de suivi-évaluation

Ce parcours est destiné aux personnes qui veulent **consulter ou corriger des enquêtes sans programmer**.

1. Demander au responsable du projet de préparer l'outil sur l'ordinateur. Il doit installer et démarrer l'application, et vérifier que le questionnaire Kobo utilisé est bien celui qui a été configuré.
2. Ouvrir le navigateur et saisir l'adresse locale communiquée par le responsable. Saisir ensuite la clé d'accès qu'il vous a fournie. Les étapes illustrées se trouvent dans le [guide de l'application](docs/notice_user_api.md).
3. Dans le menu de l'application, choisir l'action voulue : consulter un ménage, importer un nouvel export Kobo compatible, modifier une réponse, ou restaurer/supprimer un dossier.
4. Pour faire nettoyer un export complet, placer le CSV brut, le catalogue de choix et le questionnaire correspondant dans `zone_depot/`, puis demander au responsable de lancer le nettoyage. Les fenêtres de sélection s'ouvriront dans ce dossier. Ne pas remplacer les fichiers de démonstration ni supposer qu'un formulaire différent sera reconnu sans adaptation.

Une fois l'application démarrée, l'agent travaille dans la fenêtre du navigateur; il n'a pas à ouvrir le code ou à manipuler les fichiers de base de données. Le premier démarrage nécessite toutefois encore une personne technique. Un démarrage en un clic est une amélioration prévue.

Les données restent sur l'ordinateur ou le réseau local configuré pour le projet; aucune plateforme cloud n'est utilisée. L'organisation doit valider l'emplacement de stockage, les autorisations et les sauvegardes avant d'utiliser des données confidentielles.

### Parcours technique : installation, adaptation et analyse

#### 1. Préparer le formulaire et les fichiers d'entrée

Obtenir les fichiers autorisés, vérifier qu'ils correspondent à la même version de collecte, puis les déposer dans `zone_depot/` :

- l'export brut Kobo;
- le classeur questionnaire XLSForm;
- le catalogue de choix.

Les noms de variables et les règles du formulaire doivent correspondre à la configuration locale. Pour un nouveau questionnaire, prévoir une adaptation et une validation technique et métier avant le traitement complet.

#### 2. Installer l'environnement Python

Depuis PowerShell, à la racine du dépôt :

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

#### 3. Nettoyer et contrôler l'export Kobo

Lancer `src/pipeline_nettoyage.py` selon le [guide de nettoyage Kobo](docs/notice_user_pipeline.md). Le script demande les fichiers et certains paramètres de collecte, puis produit notamment :

- `outputs/donnees_nettoyees.csv`;
- `outputs/rapport_execution_m_e.md`;
- `outputs/edna_mode_capit.json`, pour la capitalisation technique.

Examiner les rapports et comparer les cas signalés aux réponses brutes et aux règles Kobo avant de considérer les données comme prêtes.

#### 4. Structurer les données et lancer l'application

Le script `src/ingest_db.py` répartit les données nettoyées dans les 11 tables SQLite. Consulter le [schéma relationnel](docs/schema_rel.md) et le [guide de la base SQL](docs/notice_user_sql.md). Sauvegarder la base et vérifier son état avant une nouvelle ingestion; éviter les modifications directes pendant que l'application fonctionne.

L'API FastAPI et l'interface Streamlit se lancent selon le [guide de l'application](docs/notice_user_api.md). L'application utilise une clé fournie par le responsable et stockée localement dans `M_E_API_KEY`. Ne jamais inscrire cette clé dans le dépôt, un notebook ou une capture d'écran.

#### 5. Analyser et restituer

Lire le [notebook des indicateurs et seuils](notebooks/04_indicateurs_doc_seuils.ipynb) avant d'interpréter un score. Les notebooks d'[exploration initiale](notebooks/01_exploration.ipynb) et d'[analyse](notebooks/03_analyse.ipynb) permettent d'examiner les distributions, les valeurs manquantes, les comparaisons et les associations.

La chaîne de travail se termine par la synthèse de veille, le tableau de bord BI, la comparaison des modèles ML et l'évaluation des risques, puis par une restitution adaptée à un public non technique. Pour interpréter les résultats, vérifier les effectifs calculables et les liens mécaniques entre certaines variables et les scores; une association ne démontre pas une causalité.

## Contexte de formation

*Ce projet individuel de fin de formation Data Analyst suit une mission de bout en bout : cadrage, qualité des données, base relationnelle, API, analyse exploratoire, veille IA/Big Data, tableau de bord, comparaison de modèles, évaluation des risques et restitution. Le cadre pédagogique permet d'expérimenter une démarche complète, avec l'objectif de la rendre utile et compréhensible pour les équipes de suivi-évaluation des ONG.*

## Architecture du dépôt

```text
.
├── README.md                 # Présentation du projet et parcours utilisateur
├── assets/                   # Visuels du dépôt
├── data_test/                # Jeux synthétiques de démonstration
├── zone_depot/               # Fichiers déposés localement avant nettoyage (non versionnés)
├── outputs_demo/             # Base, CSV et rapports de démonstration versionnés
├── outputs/                  # Résultats locaux de nettoyage et base active (ignorés)
├── cache/                    # Archives et fichiers temporaires locaux
├── notebooks/                # Exploration, nettoyage, indicateurs et analyse
├── src/
│   ├── pipeline_nettoyage.py # Contrôles et nettoyage de l'export Kobo
│   ├── ingest_db.py          # Ingestion dans la base relationnelle
│   ├── scores.py             # Calcul d'indicateurs à partir d'un DataFrame
│   ├── api.py                # API FastAPI
│   ├── app.py                # Interface Streamlit
│   └── eda.py                # Emplacement prévu pour l'EDA scriptée
├── docs/                     # Guides et documentation SQL
├── .streamlit/               # Configuration de l'interface
└── requirements.txt          # Dépendances Python
```

L'API est le service technique utilisé par l'application; Swagger est prévu pour les personnes qui développent ou testent l'API. Pour les utilisateurs métier, l'interface graphique reste le parcours le plus simple. Un lanceur en un clic ou un installateur permettrait de supprimer la dépendance actuelle au terminal lors du premier démarrage.

## Liens utiles

- **Tableau Trello :** [Projet final ONG](https://trello.com/b/2b8Sp1E4/projetfinalong)
- **Application locale :** [guide utilisateur](docs/notice_user_api.md)
- **Pipeline de nettoyage :** [guide Kobo](docs/notice_user_pipeline.md)
- **Base relationnelle :** [schéma SQL](docs/schema_rel.md) · [guide SQL](docs/notice_user_sql.md)
- **Dépendances :** [`requirements.txt`](requirements.txt)
