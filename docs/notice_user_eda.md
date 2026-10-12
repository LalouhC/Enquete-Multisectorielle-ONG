# Notice EDA : calculs et profils de questionnaires

## Une seule source des calculs

Les fonctions de score sont définies dans `src/tech_scores.py`. Le notebook `notebooks/03b_indicateurs_doc_seuils.ipynb` importe et affiche leur code pour documenter les méthodes; il ne doit pas contenir une copie modifiable de ces fonctions. Pour changer un calcul, modifier le module puis relancer le notebook de documentation et les vérifications. Le notebook `notebooks/03_analyse.ipynb` appelle le même point d’entrée, `calculer_scores`.

## Adapter une enquête connue

Chaque profil appartient au projet et se trouve dans `config/profils_questionnaires/<identifiant>.json`. Il contient les correspondances validées entre une notion utilisée par les scores et sa colonne source SQL, ainsi que les recodages de modalités nécessaires. Les colonnes personnalisées des tables sont disponibles dans l’EDA sous un nom qualifié, par exemple `wash_eau__source_eau`.

Exemple de profil :

```json
{
  "version_schema": 1,
  "identifiant": "21EBB",
  "empreinte_questionnaire": "empreinte-calculée-depuis-le-XLSForm",
  "correspondances": {
    "eau": {
      "source": "wash_eau__source_eau",
      "libelle": "Quelle est la principale source d'eau du ménage ?",
      "type": "select_one sources_eau",
      "modalites": {
        "code_puits": "Puits traditionnel",
        "code_robinet": "Robinet"
      },
      "validee": true
    }
  }
}
```

Les clés de `correspondances` sont les notions attendues par les calculs; `source` est le nom exact de la colonne présente dans le DataFrame SQL; `modalites` traduit les codes de réponse en libellés compris par les règles existantes. Une correspondance n’est utilisée que si `validee` vaut `true`. Les autres champs restent des informations descriptives et ne déclenchent pas de calcul. `enregistrer_profil_questionnaire(profil)` écrit ce document dans `config/profils_questionnaires/<identifiant>.json`.

Le profil se charge dans le notebook d’analyse en renseignant `IDENTIFIANT_PROFIL_QUESTIONNAIRE` (par exemple `"21EBB"`) et le chemin de son XLSForm dans `CHEMIN_XLSFORM_PROFIL`. Le notebook vérifie l’empreinte du formulaire et affiche les suggestions des autres profils avant d’appliquer celui sélectionné. Sans profil ni chemin XLSForm, il conserve le mode strict du questionnaire de démonstration. Avec un XLSForm sans profil, il affiche les suggestions et laisse les scores manquants au lieu d’interrompre le calcul. Avec un profil validé, `calculer_scores` tolère les notions absentes, calcule les indicateurs qui ont leurs entrées et expose leur disponibilité dans `df_scores_analyse.attrs["diagnostic_indicateurs"]`.

La taille du ménage peut être fournie directement en mappant une variable sur `taille_menage`. Si elle n’est pas fournie, le module la calcule à partir des 16 variables de composition par âge et sexe. Les indicateurs qui en dépendent restent indisponibles si aucune de ces deux sources n’est complète.

Pour créer une empreinte et consulter des suggestions à partir des profils déjà validés :

```python
from src.tech_scores import (
    calculer_empreinte_questionnaire,
    proposer_correspondances,
)

empreinte = calculer_empreinte_questionnaire(questions_xlsform, choix_xlsform)
suggestions = proposer_correspondances(questions_xlsform)
```

`questions_xlsform` et `choix_xlsform` sont les DataFrames des onglets `survey` et `choices`. L’empreinte couvre leurs colonnes et valeurs, y compris les règles du questionnaire et les choix. Les suggestions reposent sur la ressemblance des noms techniques et des libellés, avec contrôle de compatibilité du type. Elles ne comprennent pas le sens métier, ne valident pas les modalités et ne sont jamais appliquées automatiquement. Après vérification des colonnes, des modalités et des règles, enregistrer un profil avec `enregistrer_profil_questionnaire` et son empreinte calculée; conserver les profils dans le dépôt du projet permet à l’équipe de les relire et de versionner leurs changements.

## Limites à vérifier

- Les profils réutilisent les calculs existants; ils ne déduisent pas une définition, un seuil ou une pondération pour un indicateur absent. Une nouvelle méthode (par exemple SCA ou SDAM) exige sa définition, ses variables et une validation métier avant d’être ajoutée à `tech_scores.py`.
- Les codes non présents dans `modalites` ne sont pas convertis. Vérifier les recodages et les valeurs manquantes à partir des onglets `survey` et `choices` et des données nettoyées.
- Un indicateur déclaré indisponible dans le diagnostic ne doit pas être interprété comme nul. La note `méthode_incomplète` signale une formule non définie dans le module, et non une absence de vulnérabilité.
- La projection SQL du notebook d’analyse garde les tables relationnelles du projet. Le profil adapte les colonnes et les modalités de ces tables; il ne remplace pas le contrôle du schéma SQL ni la validation du questionnaire.
- Les profils sont propres au dépôt/projet. Cloner le dépôt pour une autre enquête donne une copie de ses profils; conserver des dépôts ou branches distincts permet de versionner séparément les validations. Les profils peuvent servir de références pour suggérer des correspondances à une autre enquête, mais chaque suggestion doit être confirmée.