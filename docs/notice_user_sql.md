# Guide utilisateur - Base SQL des enquêtes

Ce guide présente la base SQLite pour les agents qui consultent les données ou réalisent des analyses. Pour ajouter, modifier, supprimer ou restaurer une enquête, utiliser l'interface Streamlit; éviter toute édition directe de la base.

## 1. Où se trouve la base ?

La base est `outputs/enquete_ms.db`. Elle est locale au projet. Le CSV propre utilisé pour les listes et les échanges se trouve dans `outputs/donnees_nettoyees.csv`.

L'application Streamlit/API est le moyen recommandé pour les opérations de gestion. La base doit être sauvegardée et l'accès aux données doit respecter les règles de confidentialité de l'organisation.

## 2. Comprendre les tables

Chaque ligne possède un identifiant technique unique `id_menage`, par exemple `MENAGE_42`.

- `META_ENQUETE` : informations de suivi du passage, identifiant, date, enquêteur, village, jeton et consentement. Elle contient aussi les passages sans consentement.
- `MENAGE` : informations générales sur le ménage et son répondant.
- `STATUT_MENAGE`, `COMPOSITION_MENAGE`, `VULNERABILITE_SANTE`, `ECONOMIE_REVENU`, `SECURITE_ALIMENTAIRE`, `BIENS_AME`, `WASH_EAU`, `AGRICULTURE`, `PROTECTION` : rubriques thématiques.

Un ménage consentant est présent dans `META_ENQUETE` et dans ses tables thématiques. Un ménage non-consentant peut être présent dans `META_ENQUETE` seulement; ses informations thématiques ne doivent pas être considérées comme manquantes par erreur.

Les tables thématiques sont organisées en relation 1:1 pour la version actuelle du questionnaire. `id_menage` relie une ligne de `META_ENQUETE` à la même enquête dans les tables thématiques. Le diagramme détaillé est dans [schema_rel.md](./schema_rel.md).

## 3. Requêtes de consultation courantes

Exemples SQLite en lecture seule :

```sql
-- Nombre total de passages, y compris les refus de consentement
SELECT COUNT(*) AS nombre_passages
FROM META_ENQUETE;

-- Passages par réponse de consentement
SELECT volont, COUNT(*) AS nombre
FROM META_ENQUETE
GROUP BY volont
ORDER BY volont;

-- Ménages consentants, avec les informations de suivi et de répondant
SELECT
    meta.id_menage,
    meta.code_jeton,
    meta.date_enquete,
    meta.village,
    menage.repondant,
    menage.age,
    menage.sexe
FROM META_ENQUETE AS meta
JOIN MENAGE AS menage ON menage.id_menage = meta.id_menage
ORDER BY CAST(substr(meta.id_menage, 8) AS INTEGER);

-- Vérifier si un identifiant existe dans une table thématique
SELECT id_menage, adultincap, hand, malnut
FROM VULNERABILITE_SANTE
WHERE id_menage = 'MENAGE_42';
```

SQLite ne garantit pas l'ordre des résultats sans `ORDER BY`. Pour les identifiants `MENAGE_n`, trier numériquement avec `CAST(substr(id_menage, 8) AS INTEGER)`; un tri alphabétique placerait par exemple `MENAGE_10` avant `MENAGE_2`.

Les identifiants sont des textes; les codes jeton peuvent être stockés comme nombres. Ne pas confondre `id_menage` (identifiant interne stable de l'enregistrement) et `code_jeton` (identifiant issu du terrain, qui peut être répété dans les données historiques).

## 4. Comprendre les nombres de lignes

Les nombres entre les tables peuvent différer :

- `META_ENQUETE` contient toutes les enquêtes enregistrées, même les refus.
- Les tables thématiques ne contiennent que les ménages dont le consentement est accepté.
- Certaines rubriques peuvent ne pas avoir été présentées ou renseignées; une ligne thématique peut alors contenir des colonnes nulles.

Pour compter séparément les ménages consentants et non-consentants dans la table de suivi :

```sql
SELECT
    CASE
        WHEN lower(trim(CAST(volont AS TEXT))) IN ('oui', 'yes', 'y', 'true', 'accepted', 'accepte', 'd''accord')
          OR CAST(volont AS REAL) = 1
        THEN 'Consentement accepté'
        ELSE 'Non-consentant ou valeur à vérifier'
    END AS statut_consentement,
    COUNT(*) AS nombre
FROM META_ENQUETE
GROUP BY statut_consentement;
```

## 5. Sauvegarde et modifications

Pour une sauvegarde, arrêter les opérations en cours et copier ensemble, si nécessaire, `outputs/enquete_ms.db`, `outputs/donnees_nettoyees.csv` et `outputs/rapport_execution_m_e.md`. Noter la date de la copie. Ne pas écraser la dernière sauvegarde connue avant d'avoir vérifié la nouvelle.

Ne pas utiliser `DELETE`, `UPDATE` ou `INSERT` directement dans SQLite pour gérer un ménage. Une modification manuelle peut désynchroniser SQLite, le CSV, les archives et le rapport. Utiliser les parcours Streamlit :

- suppression : le ménage est archivé en CSV puis retiré de SQLite et du CSV propre;
- réhabilitation : l'archive nettoyée est réinsérée, replacée selon son `id_menage`, puis retirée du cache;
- modification : le champ est validé selon le questionnaire et synchronisé avec le CSV;
- nouvel export : le fichier brut passe par le pipeline avant ingestion.

Le dossier `cache/suppressions/` contient des instantanés de ménages supprimés en attente de réhabilitation. Une fois la réhabilitation réussie, l'archive est retirée du cache. Ne pas vider ce dossier manuellement sans validation du responsable des données.

## 6. Limites du modèle actuel

La base est conçue pour un seul passage par ménage dans la version actuelle. Elle ne représente pas encore le suivi longitudinal d'un même ménage à plusieurs dates. L'évolution vers plusieurs passages nécessiterait une clé de visite supplémentaire et une adaptation des relations, pas seulement l'ajout de lignes.

Les suppressions et modifications font l'objet d'une journalisation dans `outputs/rapport_execution_m_e.md`; le rapport n'est pas un journal SQL transactionnel ni un substitut à une sauvegarde.
