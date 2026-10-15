# 📊 Rapport d'Exécution et d'Audit M&E

  > **Avertissement :** Lors du lancement de la pipeline automatique, le détail de chaque diagnostic et correction est affiché en sortie de console. Ce rapport constitue un résumé synthétique des principales actions de nettoyage et de sécurisation réalisées.

  ---

  ## 📌 1. Périmètre & Traçabilité
  * **Périmètre brut initial :** 50000 enquêtes collectées.
  * **Périmètre final validé :** 50000 (dont 3365 enquêtes non-consentantes filtrées conformément à l'éthique).
  * **Structure des variables :** 109 variables au total (107 colonnes issues du questionnaire brut + 2 colonnes de contrôle technique ajoutées par le pipeline `code_initial_renseigne`, `duree_minutes`).
  * **Horodatage du lancement :** 2026-10-15 11:43:41
  * **Dernière mise à jour (Synchronisation / API) :** 2026-10-15 11:43:41

  ### 🛡️ Bilan des Actions de Nettoyage Réalisées
  * **Conformité & Éthique :** Nettoyage des données parasites et filtrafe de 3365 enquêtes ayant refusé le consentement éclairé.
  * **Gestion des Identifiants :** 0 doublon(s) strict(s) supprimé(s) et 11938 doublon(s) de jetons régénérés temporairement (code à 5 chiffres) avec traçabilité dans la colonne `code_initial_renseigne`.
  * **Standardisation Temporelle & Numérique :** Harmonisation des formats de dates, conversion de 107958 valeur(s) aberrante(s), négative(s) ou parasite(s) en valeurs nulles (`NaN`).
  * **Traitement du Texte :** Normalisation syntaxique de 55 colonne(s) (minuscules, uniformisation de la ponctuation). *Note : les accents ont été intégralement préservés.*
  * **Gestion des Vides :** Unification globale des blancs résiduels (`NaN`, chaînes vides, espaces) pour fiabiliser les analyses.
  * **Audit des durées d'enquête :** Aucune durée aberrante ou manquante détectée.

  ---

  ## ⚠️ 2. Synthèse des Risques & Anomalies du Formulaire (Kobo)
  L'analyse de la structure du questionnaire (XLSForm) et des remontées de terrain met en évidence trois piliers de configuration à corriger :
  * **Paramètre `required` (Caractère obligatoire) :** Volume important de valeurs vides ou manquantes sur des questions qui auraient dû être exigées dès la saisie (`required = yes`).
  * **Paramètre `relevant` (Conditions de saut et d'affichage) :** Présence de règles dépendantes de fonctions logiques nécessitant un contrôle strict pour éviter l'enregistrement de données orphelines.
  * **Paramètre `constraint` (Règles de validation et format) :** Présence massive de codes sentinelles (ex: `999999`, `99999`) et de valeurs négatives, prouvant l'absence de filtres bloquants ou de plages de valeurs valides sur tablettes.

  ---

  ## 💡 3. Recommandations Clés pour les Prochaines Collectes (Edna_Mode)
  Pour optimiser les futures versions du formulaire et sécuriser la collecte à la source :
  1. **Activer systématiquement `required = yes` :** Rendre obligatoires les variables clés (identifiants, consentement, localisation) pour éliminer les omissions.
  2. **Renforcer les `constraints` dans le XLSForm :** Bloquer en amont sur tablette les valeurs aberrantes (négatives, hors-plages, codes sentinelles) pour garantir l'intégrité des données brutes.
  3. **Sécuriser la logique `relevant` :** Valider l'étanchéité des conditions d'affichage pour empêcher la saisie de données non pertinentes selon le profil du ménage.
  4. **Instaurer un contrôle d'unicité :** Activer une vérification d'unicité sur le `code_jeton` dans l'application de collecte pour neutraliser les doublons dès le terrain.

  ---
  *Rapport synthétique généré automatiquement. Données brutes de capitalisation archivées dans `outputs\edna_mode_capit.json`.*
  

---

## Nouvelle exécution de mise à jour
# 📊 Rapport d'Exécution et d'Audit M&E

  > **Avertissement :** Lors du lancement de la pipeline automatique, le détail de chaque diagnostic et correction est affiché en sortie de console. Ce rapport constitue un résumé synthétique des principales actions de nettoyage et de sécurisation réalisées.

  ---

  ## 📌 1. Périmètre & Traçabilité
  * **Périmètre brut initial :** 50000 enquêtes collectées.
  * **Périmètre final validé :** 50000 (dont 0 enquêtes non-consentantes filtrées conformément à l'éthique).
  * **Structure des variables :** 107 variables au total (105 colonnes issues du questionnaire brut + 2 colonnes de contrôle technique ajoutées par le pipeline `code_initial_renseigne`, `duree_minutes`).
  * **Horodatage du lancement :** 2026-10-15 11:49:10
  * **Dernière mise à jour (Synchronisation / API) :** 2026-10-15 11:49:10

  ### 🛡️ Bilan des Actions de Nettoyage Réalisées
  * **Conformité & Éthique :** Nettoyage des données parasites et filtrafe de 0 enquêtes ayant refusé le consentement éclairé.
  * **Gestion des Identifiants :** 0 doublon(s) strict(s) supprimé(s) et 49999 doublon(s) de jetons régénérés temporairement (code à 5 chiffres) avec traçabilité dans la colonne `code_initial_renseigne`.
  * **Standardisation Temporelle & Numérique :** Harmonisation des formats de dates, conversion de 89677 valeur(s) aberrante(s), négative(s) ou parasite(s) en valeurs nulles (`NaN`).
  * **Traitement du Texte :** Normalisation syntaxique de 54 colonne(s) (minuscules, uniformisation de la ponctuation). *Note : les accents ont été intégralement préservés.*
  * **Gestion des Vides :** Unification globale des blancs résiduels (`NaN`, chaînes vides, espaces) pour fiabiliser les analyses.
  * **Audit des durées d'enquête :** Aucune durée aberrante ou manquante détectée.

  ---

  ## ⚠️ 2. Synthèse des Risques & Anomalies du Formulaire (Kobo)
  L'analyse de la structure du questionnaire (XLSForm) et des remontées de terrain met en évidence trois piliers de configuration à corriger :
  * **Paramètre `required` (Caractère obligatoire) :** Volume important de valeurs vides ou manquantes sur des questions qui auraient dû être exigées dès la saisie (`required = yes`).
  * **Paramètre `relevant` (Conditions de saut et d'affichage) :** Présence de règles dépendantes de fonctions logiques nécessitant un contrôle strict pour éviter l'enregistrement de données orphelines.
  * **Paramètre `constraint` (Règles de validation et format) :** Présence massive de codes sentinelles (ex: `999999`, `99999`) et de valeurs négatives, prouvant l'absence de filtres bloquants ou de plages de valeurs valides sur tablettes.

  ---

  ## 💡 3. Recommandations Clés pour les Prochaines Collectes (Edna_Mode)
  Pour optimiser les futures versions du formulaire et sécuriser la collecte à la source :
  1. **Activer systématiquement `required = yes` :** Rendre obligatoires les variables clés (identifiants, consentement, localisation) pour éliminer les omissions.
  2. **Renforcer les `constraints` dans le XLSForm :** Bloquer en amont sur tablette les valeurs aberrantes (négatives, hors-plages, codes sentinelles) pour garantir l'intégrité des données brutes.
  3. **Sécuriser la logique `relevant` :** Valider l'étanchéité des conditions d'affichage pour empêcher la saisie de données non pertinentes selon le profil du ménage.
  4. **Instaurer un contrôle d'unicité :** Activer une vérification d'unicité sur le `code_jeton` dans l'application de collecte pour neutraliser les doublons dès le terrain.

  ---
  *Rapport synthétique généré automatiquement. Données brutes de capitalisation archivées dans `outputs\edna_mode_capit.json`.*
  

---

## Nouvelle exécution de mise à jour
# 📊 Rapport d'Exécution et d'Audit M&E

  > **Avertissement :** Lors du lancement de la pipeline automatique, le détail de chaque diagnostic et correction est affiché en sortie de console. Ce rapport constitue un résumé synthétique des principales actions de nettoyage et de sécurisation réalisées.

  ---

  ## 📌 1. Périmètre & Traçabilité
  * **Périmètre brut initial :** 50000 enquêtes collectées.
  * **Périmètre final validé :** 50000 (dont 0 enquêtes non-consentantes filtrées conformément à l'éthique).
  * **Structure des variables :** 107 variables au total (105 colonnes issues du questionnaire brut + 2 colonnes de contrôle technique ajoutées par le pipeline `code_initial_renseigne`, `duree_minutes`).
  * **Horodatage du lancement :** 2026-10-15 12:31:06
  * **Dernière mise à jour (Synchronisation / API) :** 2026-10-15 12:31:06

  ### 🛡️ Bilan des Actions de Nettoyage Réalisées
  * **Conformité & Éthique :** Nettoyage des données parasites et filtrafe de 0 enquêtes ayant refusé le consentement éclairé.
  * **Gestion des Identifiants :** 0 doublon(s) strict(s) supprimé(s) et 49999 doublon(s) de jetons régénérés temporairement (code à 5 chiffres) avec traçabilité dans la colonne `code_initial_renseigne`.
  * **Standardisation Temporelle & Numérique :** Harmonisation des formats de dates, conversion de 89677 valeur(s) aberrante(s), négative(s) ou parasite(s) en valeurs nulles (`NaN`).
  * **Traitement du Texte :** Normalisation syntaxique de 54 colonne(s) (minuscules, uniformisation de la ponctuation). *Note : les accents ont été intégralement préservés.*
  * **Gestion des Vides :** Unification globale des blancs résiduels (`NaN`, chaînes vides, espaces) pour fiabiliser les analyses.
  * **Audit des durées d'enquête :** Aucune durée aberrante ou manquante détectée.

  ---

  ## ⚠️ 2. Synthèse des Risques & Anomalies du Formulaire (Kobo)
  L'analyse de la structure du questionnaire (XLSForm) et des remontées de terrain met en évidence trois piliers de configuration à corriger :
  * **Paramètre `required` (Caractère obligatoire) :** Volume important de valeurs vides ou manquantes sur des questions qui auraient dû être exigées dès la saisie (`required = yes`).
  * **Paramètre `relevant` (Conditions de saut et d'affichage) :** Présence de règles dépendantes de fonctions logiques nécessitant un contrôle strict pour éviter l'enregistrement de données orphelines.
  * **Paramètre `constraint` (Règles de validation et format) :** Présence massive de codes sentinelles (ex: `999999`, `99999`) et de valeurs négatives, prouvant l'absence de filtres bloquants ou de plages de valeurs valides sur tablettes.

  ---

  ## 💡 3. Recommandations Clés pour les Prochaines Collectes (Edna_Mode)
  Pour optimiser les futures versions du formulaire et sécuriser la collecte à la source :
  1. **Activer systématiquement `required = yes` :** Rendre obligatoires les variables clés (identifiants, consentement, localisation) pour éliminer les omissions.
  2. **Renforcer les `constraints` dans le XLSForm :** Bloquer en amont sur tablette les valeurs aberrantes (négatives, hors-plages, codes sentinelles) pour garantir l'intégrité des données brutes.
  3. **Sécuriser la logique `relevant` :** Valider l'étanchéité des conditions d'affichage pour empêcher la saisie de données non pertinentes selon le profil du ménage.
  4. **Instaurer un contrôle d'unicité :** Activer une vérification d'unicité sur le `code_jeton` dans l'application de collecte pour neutraliser les doublons dès le terrain.

  ---
  *Rapport synthétique généré automatiquement. Données brutes de capitalisation archivées dans `outputs\edna_mode_capit.json`.*
  