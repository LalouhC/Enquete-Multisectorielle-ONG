# Notice d'Utilisation - Pipeline de Nettoyage et d'Audit KoboToolbox (Version Bêta)

## 1. Structure et Architecture du Projet (Périmètre Pipeline)
Cette section se concentre exclusivement sur les dossiers et fichiers directement liés au fonctionnement de la pipeline de nettoyage. Les futurs modules d'analyse ou de modélisation viendront s'ajouter dans des répertoires dédiés sans impacter ce noyau :

`data/` : Contient les données brutes de terrain (`.csv`) et le dictionnaire de formulaire d'enquête (`.xlsx`).

`src/` : Héberge les scripts Python autonomes de la pipeline (nettoyage, audits, génération des rapports).

`notebooks/` : Réservé au prototypage et à l'exploration (`01_exploration.ipynb`, etc.).

`docs/` : Centralise la documentation technique et la présente notice d'utilisation.

`outputs/` : Stocke les livrables générés automatiquement (rapports exécutifs `.md` et logs JSON pour l'agent Edna_Mode).

## 2. Processus de Collecte et Prérequis Utilisateur
### Rôle du Chargé de Suivi-Évaluation (M&E)
Conception du Questionnaire : Le M&E crée ou met à jour son formulaire sur KoboToolbox. Ce fichier au format Excel (`.xlsx`) doit obligatoirement structurer le formulaire sur deux onglets distincts :

- Un onglet `survey` recensant les variables, leurs labels, leurs types et leurs contraintes.

- Un onglet `choices` contenant le codage des réponses (choix uniques ou multiples).

Export des Données de Terrain : Après les entretiens, le M&E extrait la base de données brute des réponses (au format `.xlsx` ou convertie en `.csv` selon la volumétrie).

### Intégration dans la Pipeline (Cas du Projet & Formats)
Le script automatise le croisement entre la base de données brute des enquêtes et le dictionnaire du questionnaire pour décoder les choix et auditer la structure.

Spécificité du prototype actuel : Dans le cadre de notre projet, l'onglet des choix a été extrait et isolé sous forme de fichier `.csv` distinct (`code_choix.csv`), tandis que le questionnaire global est chargé en .`xlsx`.

⚠️ Alerte critique sur les noms de colonnes :
*Pour que la pipeline s'exécute sans erreur, les noms des colonnes de votre dictionnaire de questionnaire doivent strictement correspondre aux standards de nommage attendus par les scripts. Si vous utilisez un fichier aux dénominations personnalisées ou non conformes aux exports natifs Kobo, la pipeline rejettera les colonnes non reconnues ou générera des erreurs d'exécution. Veillez à bien harmoniser vos en-têtes en amont.*

## 3. Pipeline de Nettoyage Automatisé
**Portabilité**
Conçue pour s'adapter de manière générique à tout export respectant les normes de codage KoboToolbox.

**Adaptation Contextuelle**
Le jeu de données actuel, volontairement altéré pour simuler des conditions réelles complexes, intègre des lignes de traitement spécifiques qui n'impactent pas la réutilisabilité globale du script sur de futurs projets conformes.

**Exploration & Masquage**
L'analyse exploratoire met en évidence des colonnes correspondant aux groupes thématiques. Celles-ci ainsi que les entrées vides sont masquées pour alléger l'analyse sur les datasets restreints.

*⚠️ Attention : Si vous utilisez un fichier ne correspondant pas aux normes Kobo, veuillez vérifier que ces règles de masquage ciblées ne suppriment pas par inadvertance des variables utiles.*

## 4. Limites et Statut Bêta
**Périmètre Restreint**
Cet outil constitue un prototype. Il repose sur un questionnaire allégé.

**Règles Kobo Non Exhaustives**
L'intégralité des contraintes avancées, des logiques de sauts complexes (relevant) ou des validations natives de Kobo n'a pas été transposée dans cette version bêta.

**Vigilance Utilisateur**
En cas d'utilisation sur un fichier non conforme aux standards Kobo, s'assurer que les règles de filtrage ciblées ne suppriment pas par inadvertance des variables analytiques.