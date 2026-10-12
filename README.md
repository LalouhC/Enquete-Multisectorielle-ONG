# Enquête multisectorielle — qualité des données, vulnérabilité et aide à la décision

![Échange lors d’une enquête de terrain](assets/photo-enquete-terrain.png)

> **Prototype bêta de fin de formation, conçu pour explorer une méthodologie concrète au service des ONG.** L'approche n'est pas validée par les pairs. L'outil aide les équipes à analyser les informations; il ne décide pas à leur place.

## 🎯 Contexte et problématique métier

Les équipes de suivi-évaluation des ONG exploitent des questionnaires et des exports produits avec <a href="https://www.kobotoolbox.org/"><img src="assets/kobotoolbox-logo.svg" alt="KoboToolbox" width="110" /></a>, repèrent les erreurs qui fragilisent les données, comprennent les besoins des ménages et partagent rapidement des résultats compréhensibles avec les équipes opérationnelles. Le projet transforme les fichiers d'enquête en données nettoyées, en analyses utiles et en informations mobilisables pour la décision humanitaire.

Pour répondre à ce besoin, le projet s'articule autour de la question suivante :

**Comment identifier et prédire le niveau de vulnérabilité critique des ménages à partir de leurs caractéristiques socio-démographiques et de leurs conditions de vie pour optimiser le ciblage de l'aide humanitaire ?**

*Analyse prédictive des facteurs de vulnérabilité multisectorielle et optimisation de la collecte et du traitement des données.*

## 🧰 Les outils proposés

Le projet donne aux équipes les moyens de :

- préparer et nettoyer des exports Kobo de plusieurs milliers de lignes, puis comprendre les principales erreurs techniques et incohérences métier à corriger;
- examiner les vulnérabilités par secteur et selon les caractéristiques socio-démographiques des ménages, sans fusionner tous les secteurs en un score opaque;
- visualiser les indicateurs dans un tableau de bord interactif, pour repérer les groupes ou zones qui nécessitent une analyse plus approfondie;
- comparer des modèles de machine learning qui classent les niveaux de vulnérabilité observés et documenter leurs limites et leurs risques;
- consulter, importer et corriger les dossiers dans une interface protégée, puis capitaliser les constats utiles pour les prochaines collectes.

> ⚠️ **Questionnaires et variables :** plusieurs correspondances de noms, variables analysées, règles et seuils sont définis spécifiquement pour le questionnaire de démonstration. Avant d'importer un autre formulaire, vérifier ses noms de colonnes, choix, conditions et indicateurs; faire adapter le paramétrage par une personne technique lorsque la structure diffère. Le nettoyage repère aussi les champs de texte libre, compte leurs réponses distinctes et harmonise la casse, la ponctuation et les espaces. Il s'agit d'un prétraitement technique, pas d'une analyse qualitative du sens des réponses ni d'une anonymisation garantie.

## 🧭 Méthodologie : entre analyse multisectorielle issue du JIAF et rapidité des MSA

Le **JIAF 2.0** (*Joint and Intersectoral Analysis Framework*) est un cadre méthodologique approuvé par le Comité permanent interorganisations (IASC). Il structure l'analyse conjointe et intersectorielle des besoins humanitaires et des risques de protection. Il combine des données quantitatives et qualitatives pour estimer combien de personnes ont besoin d'assistance, caractériser la nature, les facteurs déterminants et la sévérité de leurs besoins, et comprendre leur chevauchement entre secteurs. Ses résultats éclairent la planification stratégique de la réponse humanitaire, notamment les *Humanitarian Needs and Response Plans* (HNRP). Le [manuel technique JIAF 2.0 publié par OCHA](https://www.unocha.org/publications/report/world/joint-and-intersectoral-analysis-framework-jiaf-2-technical-manual-july-2024) décrit cette démarche.

Le projet applique cette logique de lecture multisectorielle aux données des ménages, avec des indicateurs sectoriels documentés et des croisements qui aident à comprendre les vulnérabilités combinées. **Ces indicateurs ne couvrent pas toutes les mesures possibles en analyse multisectorielle** : leur périmètre est déterminé par les questions et les variables du questionnaire simplifié retenu pour la démonstration, ainsi que par la logique des évaluations rapides MSA, qui privilégie la collecte d'un ensemble ciblé d'informations dans un temps limité. L'absence d'un indicateur reflète donc aussi les limites du questionnaire et du périmètre de collecte, et ne signifie pas nécessairement que le besoin correspondant est absent.

Le projet répond au besoin de rapidité des **évaluations multisectorielles (MSA, *Multi-Sectoral Assessments*)**, qui fournissent un aperçu opérationnel des besoins. Le positionnement associe ainsi une analyse structurée inspirée du JIAF à un traitement plus rapide des données MSA. Le prototype ne constitue pas une mise en œuvre complète du JIAF et ne remplace ni l'analyse intersectorielle coordonnée ni le jugement des équipes.

## 🧪 Démo : des données aux résultats

Cette démo permet de voir concrètement comment le projet transforme des données d'enquête en informations utiles aux équipes de suivi-évaluation, et quels résultats elles peuvent consulter.

Les outils ont été façonnés à partir de deux bases d'essai et d'un questionnaire simplifié : l'une des bases sert à tester les erreurs de données, l'autre reprend les proportions d'une enquête menée en République Démocratique du Congo. Ces essais ont permis d'adapter les vérifications et les analyses aux informations réellement recueillies dans une enquête multisectorielle. Concrètement, les réponses passent du fichier de collecte au nettoyage et à un rapport de vérification, puis à des résultats par secteur, à une classification des niveaux de vulnérabilité et à une présentation visuelle pour aider les équipes à décider. Des exemples des fichiers traités et des résultats sont réunis dans `outputs_demo/`.

### 1. Bases et questionnaire

Le projet utilise deux bases synthétiques de **50 000 ménages chacune**. La première, `enquete_vul_brute.csv`, éprouve le nettoyage avec des erreurs techniques volontaires et vérifie le traitement d'un fichier volumineux. La seconde, `enquete_vul_brute_terrain.csv`, est elle aussi une base synthétique de **50 000 ménages**; elle reproduit les proportions observées lors d'une enquête réellement menée auprès d'environ **3 000 ménages en 2021**, dans la province de l'Équateur, en République Démocratique du Congo, sur un axe d'intervention précis. Elle ne contient ni l'export original ni les dossiers individuels des ménages enquêtés. Comme certaines colonnes du questionnaire de démonstration ne correspondent pas directement aux variables de l'enquête source, les valeurs associées à ces colonnes restent fictives : toutes les statistiques de la seconde base ne sont donc pas des observations de terrain.

Le questionnaire de démonstration est un XLSForm fictif, structuré avec les onglets `survey` et `choices`. Le catalogue `code_choix.csv` est également fourni dans le projet; pour ce formulaire, il est facultatif puisque les listes figurent déjà dans `choices`. La [documentation KoboToolbox sur la création d'un formulaire XLSForm](https://github.com/kobotoolbox/docs/blob/master/source/getting_started_xlsform.md) présente la structure du questionnaire et de ses listes de choix.

### 2. Chaîne de traitement et livrables

Le traitement suit les étapes suivantes :

1. Le script de nettoyage contrôle le fichier CSV brut avec le XLSForm et produit le CSV nettoyé, le rapport d'exécution et les données de capitalisation.
2. Le script d'ingestion répartit les données nettoyées dans la base relationnelle SQLite.
3. Le script d'analyse lit les tables SQL, calcule les indicateurs sectoriels et produit les tableaux de métriques et les visualisations.
4. Le script de machine learning entraîne et compare au moins deux modèles avec GridSearch, évalue leur capacité à classer les niveaux de vulnérabilité et consigne les performances et les limites du modèle retenu.
5. Le tableau de bord BI restitue les résultats autour d'au moins trois axes d'analyse et de quatre KPI, dont une carte, puis fournit un support pour la présentation décisionnelle.

### 3. Où trouver les bases et les livrables ?

| Emplacement | Contenu |
|---|---|
| `data_test/enquete_vul_brute.csv` | Première base synthétique, utilisée pour éprouver le nettoyage technique. |
| `data_test/enquete_vul_brute_terrain.csv` | Seconde base synthétique, générée à partir des proportions de l'enquête réelle de 2021. |
| `data_test/Questionnaire Vulnérabilités Fictif.xlsx` | Questionnaire de démonstration et listes de choix dans l'onglet `choices`. |
| `data_test/code_choix.csv` | Copie facultative du catalogue de choix du XLSForm. |
| `outputs_demo/donnees_nettoyees.csv` | CSV nettoyé issu de la seconde simulation. |
| `outputs_demo/enquete_ms.db` | Base SQLite issue de la seconde simulation. |
| `outputs_demo/rapport_execution_m_e.md` | Rapport contenant des éléments des traitements des deux jeux de test. |
| `outputs_demo/edna_mode_capit.json` | Données de capitalisation liées aux deux jeux de test. |
| `outputs_demo/analyse/` | Tableaux de métriques, visualisations et synthèses issus de l'analyse multisectorielle. |
| `outputs_demo/ml/` | Résultats GridSearch, comparaison des modèles, métriques et évaluation du modèle retenu. |
| `outputs_demo/bi/` | Tableau de bord décisionnel et support de restitution des indicateurs. |

Les scripts ayant généré les bases ne sont pas inclus dans le dépôt. Les réponses individuelles originales de l'enquête réelle ne sont pas publiées.

### ⚠️ Interprétation et limites de transposition

Les bases de démonstration sont synthétiques et ne reprennent pas les enregistrements individuels de l'enquête réelle. Elles ne contiennent pas intentionnellement de données personnelles identifiantes issues de cette collecte; le risque d'identifier ses répondants à partir de ces seuls fichiers de démonstration ne s'applique donc pas. La seconde base reflète toutefois des proportions observées en 2021 dans un axe et une zone géographique précis; elle ne décrit pas nécessairement la situation actuelle et ne permet pas de généraliser les résultats à d'autres populations, lieux ou périodes. Les performances et classements du modèle dépendent également des données utilisées. Ces résultats illustrent la démarche et les outils; ils ne constituent pas une estimation représentative de la situation humanitaire.

Les indicateurs sont calculés séparément par secteur, avec leurs définitions et seuils documentés. Le traitement local évite l'envoi automatique des données vers un service cloud, mais ne garantit pas à lui seul l'absence de risque : des données réelles, notamment des textes libres ou des profils rares, peuvent permettre une identification directe ou partielle. Avant leur utilisation, vérifier les autorisations, limiter l'accès aux personnes habilitées et sécuriser l'ordinateur, le réseau local et les sauvegardes.

## 🧭 Comment utiliser le projet ?

Le parcours ci-dessous explique par où commencer et quelle action choisir. Des notices utilisateur donnent les consignes pas à pas pour les manipulations; elles sont liées dans les étapes correspondantes et dans les liens utiles.

### 👥 Parcours de l'agent·e M&E

Lors de la première utilisation du projet, une personne technique installe et prépare l'outil sur votre ordinateur. Pour les utilisations suivantes, vous pouvez utiliser ses fonctions en autonomie : double-cliquez sur le raccourci **« Ouvrir l'outil M&E »** pour afficher la page d'accueil dans le navigateur. Aucun code ni commande n'est à saisir; les notices utilisateur vous accompagnent pas à pas au besoin.

Pour traiter une nouvelle enquête, l'agent·e choisit **« Déposer et nettoyer une enquête »**. La page indique clairement où placer le fichier d'enquête et son questionnaire correspondant, dans la **zone de dépôt** du projet, puis permet de lancer le nettoyage et de consulter son rapport. Pour consulter ou corriger des dossiers déjà importés, l'agent·e choisit **« Gérer les enquêtes »**.

| Espace de l'interface | Ce que l'agent·e y fait |
|---|---|
| **📥 Déposer et nettoyer** | Placer l'export Kobo et le questionnaire correspondant dans la zone de dépôt, lancer le nettoyage, consulter le résumé des contrôles et télécharger le rapport en DOCX; retrouver également le rapport d'exécution complet. |
| **🗂️ Gérer les enquêtes** | Consulter, importer, modifier, supprimer ou restaurer un dossier depuis les fonctions de gestion des enquêtes. |
| **📊 Analyser** | Explorer les indicateurs sectoriels, les répartitions, les comparaisons et les associations entre les caractéristiques des ménages. |
| **🧠 Aide à la décision** | Examiner la classification produite par le modèle retenu, ses performances et ses limites. |
| **📈 Tableau de bord** | Visualiser les KPI, les tendances et les zones d'intervention dans le tableau de bord BI et sa présentation de restitution. |

Après chaque traitement, les résultats apparaissent dans Streamlit, dans un espace **« Mes résultats »** : l'agent·e peut y consulter les rapports et télécharger les fichiers utiles, notamment le rapport au format DOCX. Ces boutons et liens donnent accès aux fichiers réellement enregistrés, pour le travail en cours, dans le dossier local `outputs/`. L'agent·e n'a donc pas besoin d'ouvrir ce dossier sur l'ordinateur. Le traitement reste sur l'ordinateur ou le réseau local configuré; les accès sont réservés aux personnes habilitées et les données ne sont pas envoyées vers une plateforme cloud.

### 🛠️ Parcours technique : installation, adaptation et analyse

Cette section présente deux usages du projet : travailler directement dans VS Code et accompagner un·e agent·e non technique dans l'utilisation de l'application Streamlit en local.

#### Préparation commune : poste, code, accès et données

1. **Installer les outils.** Installer [Git](https://git-scm.com/downloads), [Visual Studio Code](https://code.visualstudio.com/download) et [Python](https://www.python.org/downloads/). Ajouter les extensions **Python** et **Jupyter** à VS Code pour utiliser les notebooks.

2. **Récupérer le projet.** Depuis PowerShell, cloner le dépôt et ouvrir le dossier :

```powershell
git clone https://github.com/LalouhC/Enquete-Multisectorielle-ONG.git
cd Enquete-Multisectorielle-ONG
code .
```

Si `code .` n'est pas disponible, ouvrir le dossier cloné depuis **Fichier > Ouvrir le dossier** dans VS Code. Les commandes s'exécutent depuis la racine du projet, celle qui contient `src`, `notebooks`, `data_test` et `zone_depot`.

3. **Vérifier les accès et les données.** Si le projet est installé pour un·e collègue, confirmer avec la personne responsable les droits d'accès, la clé locale `M_E_API_KEY`, les sauvegardes et l'emplacement des fichiers. Ne jamais inscrire la clé dans le dépôt, un notebook ou une capture d'écran.

   Pour une enquête réelle, réunir les fichiers autorisés correspondant à **une seule et même version** du formulaire :

   - un export brut Kobo au format CSV;
   - le questionnaire XLSForm correspondant, avec l'onglet `survey`;
   - le catalogue `code_choix.csv` si les choix ne figurent pas dans l'onglet `choices`.

   Déposer ces fichiers dans `zone_depot/`. Pour tester le nettoyage, choisir un seul CSV de `data_test/`. Vérifier que ses noms de variables concordent avec ceux du XLSForm. Le questionnaire de démonstration est simplifié : avant d'utiliser un autre formulaire, vérifier ses règles `relevant`, `constraint`, `required`, ses choix, ses calculs et le consentement. Une cellule vide peut correspondre à une question non applicable, une non-réponse, un refus ou une valeur neutralisée au nettoyage; l'interpréter à partir du formulaire et des données brutes.

4. **Créer l'environnement Python.** Depuis la racine du projet, choisir une méthode :

**Méthode recommandée : `.venv`**

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Méthode alternative : `uv`**

Installer d'abord [`uv`](https://docs.astral.sh/uv/getting-started/installation/), puis exécuter :

```powershell
uv venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

Sélectionner `.venv` comme interpréteur Python dans VS Code. Réinstaller les dépendances après une modification de `requirements.txt`.

#### A. Utiliser les scripts et notebooks sans Streamlit

Ce parcours convient à la personne qui traite et analyse elle-même les données. Il ne nécessite pas de démarrer l'API ou l'application Streamlit.

1. **Nettoyer l'export.** Lancer le pipeline depuis la racine :

```powershell
.\.venv\Scripts\python.exe .\src\pipeline_nettoyage.py
```

Les fenêtres s'ouvrent dans `zone_depot/`. Le script produit `outputs/donnees_nettoyees.csv`, `outputs/rapport_execution_m_e.md` et `outputs/edna_mode_capit.json`. Suivre la [notice de nettoyage Kobo](docs/notice_user_pipeline.md).

2. **Contrôler et charger les données.** Lire le rapport, comparer les anomalies au formulaire et aux réponses brutes, puis conserver une copie des entrées et résultats à archiver. Charger ensuite le CSV propre dans SQLite :

```powershell
.\.venv\Scripts\python.exe .\src\ingest_db.py
```

Le script lit `outputs/donnees_nettoyees.csv` et met à jour `outputs/enquete_ms.db`. Consulter le [schéma relationnel](docs/schema_rel.md) et la [notice SQL](docs/notice_user_sql.md); sauvegarder la base avant une nouvelle ingestion.

3. **Analyser les indicateurs.** Lire les [définitions et seuils](notebooks/04_indicateurs_doc_seuils.ipynb), puis lancer le script qui lit la base SQL et enregistre métriques et graphiques dans `outputs/analyse/` :

```powershell
.\.venv\Scripts\python.exe .\src\eda.py
```

Le notebook [03_analyse.ipynb](notebooks/03_analyse.ipynb) complète l'examen des distributions, des comparaisons et des associations. Interpréter les effectifs et les limites de chaque score; une association ne démontre pas une causalité.

4. **Entraîner et évaluer le modèle ML.** Lancer le script `src/machine_learning.py` :

```powershell
.\.venv\Scripts\python.exe .\src\machine_learning.py
```

Le script compare au moins deux modèles avec GridSearch, évalue la classification des niveaux de vulnérabilité et enregistre les métriques dans `outputs/ml/`. Vérifier les biais, la qualité des variables et les limites de transposition avant d'utiliser les prédictions pour le ciblage.

5. **Actualiser le tableau de bord BI.** Installer Power BI Desktop, ouvrir `outputs/bi/tableau_de_bord.pbix` et actualiser les données d'analyse et de modélisation. Vérifier les filtres, au moins trois axes d'analyse, les quatre KPI et la carte avant la restitution. Les livrables de démonstration sont rangés dans `outputs_demo/bi/`.

#### B. Installer Streamlit pour un·e collègue non technique

Ce parcours sert à préparer l'ordinateur de l'agent·e. L'installation technique est faite une seule fois; l'agent·e utilise ensuite l'interface dans son navigateur, sans ouvrir VS Code ni un terminal.

1. **Préparer les données de départ.** Pour une démonstration, copier `outputs_demo/enquete_ms.db` et `outputs_demo/donnees_nettoyees.csv` dans `outputs/`. Pour une enquête réelle, exécuter d'abord les étapes A.1 et A.2 afin de nettoyer et charger les données.

2. **Configurer les accès.** Définir localement la clé `M_E_API_KEY`, vérifier les droits de l'agent·e et confirmer que l'application utilise la base attendue. Ne pas enregistrer la clé dans GitHub, le code ou un fichier publié.

3. **Tester l'installation.** Lancer le raccourci **« Ouvrir l'outil M&E »**; il démarre l'API et Streamlit et ouvre l'interface dans le navigateur. Depuis PowerShell, le même démarrage s'effectue avec :

```powershell
.\scripts\lancer_application.ps1
```

Vérifier le parcours avec l'agent·e : dépôt d'une enquête, lecture du rapport, consultation des résultats et accès aux fonctions autorisées. La [notice de l'application](docs/notice_user_api.md), la [notice SQL](docs/notice_user_sql.md) et la [notice de nettoyage Kobo](docs/notice_user_pipeline.md) détaillent les manipulations correspondantes.

## 🎓 Contexte de formation

*Ce projet individuel de fin de formation Data Analyst suit une mission de bout en bout : cadrage, qualité des données, base relationnelle, API, analyse exploratoire, veille IA/Big Data, tableau de bord, comparaison de modèles, évaluation des risques et restitution. Le cadre pédagogique permet d'expérimenter une démarche complète, avec l'objectif de la rendre utile et compréhensible pour les équipes de suivi-évaluation des ONG.*

## 🗂️ Architecture du dépôt

```text
.
├── README.md                 # Présentation du projet et parcours utilisateur
├── assets/                   # Visuels du dépôt
├── data_test/                # Jeux synthétiques de démonstration
├── zone_depot/               # Fichiers déposés localement avant nettoyage (non versionnés)
├── outputs_demo/             # Résultats de démonstration : nettoyage, analyse, ML et BI
│   ├── analyse/
│   ├── ml/
│   └── bi/
├── outputs/                  # Résultats locaux de nettoyage et base active (ignorés)
├── cache/                    # Archives et fichiers temporaires locaux
├── notebooks/                # Exploration, nettoyage, indicateurs et analyse
├── src/
│   ├── pipeline_nettoyage.py # Contrôles et nettoyage de l'export Kobo
│   ├── ingest_db.py          # Ingestion dans la base relationnelle
│   ├── eda.py                # Analyse exploratoire et calcul des indicateurs
│   ├── machine_learning.py   # Comparaison et évaluation des modèles
│   ├── scores.py             # Calcul d'indicateurs à partir d'un DataFrame
│   ├── api.py                # API FastAPI
│   └── app.py                # Interface Streamlit
├── scripts/
│   └── lancer_application.ps1 # Démarrage local de l'API et de l'interface
├── docs/                     # Guides, documentation SQL et schéma MPD
├── .streamlit/               # Configuration de l'interface
└── requirements.txt          # Dépendances Python
```

L'API assure les échanges entre l'interface et la base de données. La documentation Swagger s'adresse aux personnes qui développent ou testent ces échanges; les équipes métier utilisent l'interface graphique et son lanceur local.

## 🔗 Liens utiles

- **Tableau Trello :** [Projet final ONG](https://trello.com/b/2b8Sp1E4/projetfinalong)
- **Application locale :** [guide utilisateur](docs/notice_user_api.md)
- **Pipeline de nettoyage :** [guide Kobo](docs/notice_user_pipeline.md)
- **Base relationnelle :** [schéma relationnel](docs/schema_rel.md) · [schéma visuel MPD](docs/schema_MPD.svg) · [guide SQL](docs/notice_user_sql.md)
- **Dépendances :** [`requirements.txt`](requirements.txt)
