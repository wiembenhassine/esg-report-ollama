# Bilan des tests et des corrections — esg-report-ollama

Document de suivi (tests du 4 octobre 2026, corrections du 5 octobre 2026). Toutes les preuves
viennent de commandes réellement lancées sur le PC du projet (Windows, Python 3.14.7, Ollama 0.35.0,
`llama3.1:8b` et `nomic-embed-text`, CPU i5-12450H sans GPU, 15,7 Go de RAM).

## 1. Bilan des 8 tests (avant corrections)

| Test | Résultat | Preuve | Correction |
|---|---|---|---|
| 1. Installation | **OK** | `pip check` : aucun conflit ; 10 dépendances installées ; 14 modules s'importent ; `ollama list` : `llama3.1:8b`, `nomic-embed-text` ; l'API d'embeddings renvoie un vecteur de 768 dimensions | — |
| 2. Validation des données | **OK** | `python -m esg.validate` : 191 lignes, 191 valides (177 notées, 14 sans score attendu : 12 préfaces PRE + PA-4/PA-5 non applicables pour TU Dublin), **0 erreur** ; contrôle indépendant sans le code du projet : mêmes chiffres | — |
| 3. Rapport de Dublin | **Fonctionne, qualité insuffisante** | `python -m esg.pipeline tudublin --no-cache` : 99,5 min, note du juge affichée à chaque tentative ; 7 sections validées, 1 à relire (stratégie) ; `rapport_tudublin.docx` créé (14 parties, 25 tableaux) | Corrections 1, 2, 5 |
| 4. Exactitude des chiffres | **OK** | 10 chiffres tirés au hasard (graine 3606) dans le rapport de Dublin : **10/10 identiques** à `combined_esg_dataset.csv`, sur la bonne ligne du rapport | — |
| 5. Le juge face à un texte faux | **OK** | « TU Dublin obtient 15/5… neutralité carbone… éoliennes » : bloqué par le garde-fou (« 15/5 ») ; soumis quand même au juge : **note 1/5, fidélité 0 %, REJETÉ**, 3 affirmations sur 3 non supportées | — |
| 6. Le chat | **Problème** | Eau de Dublin : OK (« non disponible » + 4,33/6 vérifié) ; biodiversité de Cork : « non disponible » à tort ; énergie : chiffres justes (5,62/10 et 6,34/10 vérifiés) mais lien faux avec « Platinum/Gold » ; arbres : « non disponible » mais par une erreur de mots-clés ; biodiversité de Dublin : se trompe aussi | Corrections 3, 4 |
| 7. Autres sorties | **OK pour ce qui existe** | tableau de bord, correspondances GRI/TCFD/ESRS, démo du garde-fou : fonctionnent. **Il n'existe ni module de recommandations ni application web** dans le projet | À décider |
| 8. Dépôt Git | **Problème** | GitHub avait 5 commits de retard (clone sans validation, chat, Word, TCFD/ESRS) ; installation depuis zéro OK (86 tests) mais sur le même PC ; dépôt 3,8 Mo, aucun secret ni chemin personnel ; e-mails de personnes réelles uniquement dans les données brutes de Hakim (pages STARS publiques) | Correction 6 |

## 2. Défaut majeur trouvé : marqueurs détournés

Les chiffres venaient bien du CSV, mais le modèle les plaçait dans un **faux contexte** :

| Section (Dublin) | Brouillon du modèle | Texte final | Réalité |
|---|---|---|---|
| Parties prenantes | `environ {{ EN5_score }} étudiants sur {{ EN5_max }}` | « environ 4,5 étudiants sur 8 » | score STARS du crédit EN-5 (4,5/8 points) |
| Stratégie | `de l'ordre de {{ PA2_max }} % d'ici {{ PA2_max }}` | « 6 % d'ici 6 » | points maximum de PA-2 |
| Social | `inférieur à {{ PA9_max }}` | « revenu inférieur à 3 » | points maximum de PA-9 |
| Enseignement | `{{ AC1_score }} sur {{ AC1_max }} sont axés` | « 14 sur 14 projets » | points STARS de AC-1 |
| Gouvernance | `{{ GOV_pct }} %` ; `(GOVPct)` | « 97,0 % % » ; « (GOVPct) » ; « 10,67/11 = niveau maximal » | 97 % = niveau **élevé** |

Le juge n'en a détecté aucun.

## 3. Règle de validation d'une section

1. **Garde-fou (code)** : texte rejeté si le modèle écrit un nombre que le code ne peut pas retirer sans
   supprimer plus de 40 % du texte, ou s'il enfreint une règle bloquante (anglais, « conforme aux normes
   GRI », « l'université n'a pas fourni… », moins de 90 ou plus de 500 mots).
2. **Juge (Ollama)** : note de 1 à 5, au plus 6 affirmations marquées supportées ou non
   (**fidélité** = part supportée), liste de violations.
3. **Recoupement (code)** : les violations que le code peut prouver fausses sont écartées.
4. **Décision** : validée si **fidélité ≥ 80 %** ET (**note ≥ 3/5** OU toutes les violations écartées).
   Sinon réécriture (2 tentatives au plus).
5. **Après 2 refus** : « à relire » si la meilleure version atteint 60 % de fidélité ; sinon texte de
   repli écrit par le code.

Seuils choisis de façon raisonnée, non calibrés sur des exemples corrigés.
Exemple : la gouvernance de Dublin passe avec 2/5 car sa fidélité est de 100 % et sa seule violation
(« prétend la conformité GRI 2-9 ») est fausse, ce que le code a vérifié.

## 4. Fiabilité du juge — AVANT corrections (8 sections de Dublin, test 3)

Comptage à la main contre les textes STARS ; une autre personne pourrait compter un peu différemment.

| Section | Décision | Vraies erreurs (relecture) | Vues par le juge | Fausses alertes |
|---|---|---|---|---|
| Organisation | validée 4/5, 100 % | 0 | — | 1 |
| Thèmes matériels | validée 4/5, 83 % | 3 : « Services de l'État (SEC) » ; « a identifié les thèmes matériels » ; « d'ici » sans date | 0 | 1 (phrase « conforme GRI » inventée par le juge) |
| Gouvernance | validée 2/5, 100 % | 3 : « 10,67/11 = niveau maximal » ; « 97,0 % % » et « (GOVPct) » ; « technologie de la gouvernance » | 0 | 1 (écartée par le code) |
| Stratégie | à relire 3/5, 67 % | 2 : « Comité des services communs (SEC) » ; « 6 % d'ici 6 » | 1 | 2 |
| Parties prenantes | validée 3/5, 83 % | 2 : « 4,5 étudiants sur 8 » ; développé de « SLWC+ » inventé | 0 | 1 |
| Environnement | validée 4/5, 100 % | 2 : « de watt/unit », « de MWh » (phrases vidées) ; « champ d'application 1 » pour les déchets | 0 | 1 |
| Social | validée 2/5, 83 % | 2 : « revenu inférieur à 3 » ; droits « des étudiants » non sourcé | 1 | 1 (écartée par le code) |
| Enseignement | validée 4/5, 100 % | 2 : « 14 sur 14 projets » ; restes « (Ref ) » | 0 | 1 |
| **Total** | **7 validées, 1 à relire** | **16** | **2 (12 %)** | **9, dont 3 écartées par le code** |

Conclusion : le juge 8B ne suffit pas à garantir le sens ; les garanties solides viennent du code.

## 4 bis. Fiabilité du juge — APRÈS corrections (mêmes 8 sections de Dublin, 5 octobre au soir)

Même méthode : relecture à la main de chaque phrase contre les textes STARS de TU Dublin.
Régénération complète (`--no-cache`) avec le code de `66b99dc`, puis la section en repli rejouée
avec `7e6d242`.

| Section | Décision | Vraies erreurs (relecture) | Vues par le juge | Fausses alertes |
|---|---|---|---|---|
| Organisation | validée 4/5, 100 % | 1 : « un score STARS global de un score STARS global de 83,35 » (texte du marqueur répété) | 0 | 1 |
| Thèmes matériels | validée 2/5, 100 % (rejouée) | 2 : « Race Equality Plan » traduit par « Plan de l'égalité des sexes » ; « tous les niveaux de prise de décision » au lieu des niveaux de direction | 0 | 1 (« conforme GRI », écartée par le code) |
| Gouvernance | validée 4/5, 100 % | 3 : phrase sur le TU Act répétée ; « étaient : » suivi d'aucune liste ; « membre de l'Union des étudiants » (la source dit membre étudiante de troisième cycle) | 0 | 1 |
| Stratégie | validée 4/5, 100 % (2 tentatives) | 3 : « a signé le Climate Action Plan » (la source : objectifs alignés sur le CAP) ; « neutre en carbone d'ici 2030 » (2050 dans la source ; 2030 = baisse de 51 %) ; « a signé la charte » de la SDG Literacy CoP | 0 (phrase CAP visée, mais pour une fausse raison et jugée « supportée ») | 1 |
| Parties prenantes | validée 4/5, 100 % | 3 : marqueur PA-3 répété (« niveau maximal points sur 4 points STARS sur 4… ») ; restes « (Ref, Ref) » ×3 ; « l'université n'a pas rendu publics tous les partenariats » (formulation négative, généralisation) | 0 | 1 |
| Environnement | validée 4/5, 100 % (2 tentatives) | 8 : « l'université de Dublin » (autre établissement) ; « scores élevés » en énergie et eau (niveaux intermédiaires) ; « Cette énergie… » orpheline après une phrase retirée ; eau de pluie répétée sous « Énergie » ; compteurs d'eau « au niveau des bâtiments » (un seul bâtiment) ; compost « utilisé comme engrais pour les jardins » ; « système de gestion des véhicules » ; « système de gestion environnementale » (inventés) | 1 (« scores élevés ») | 0 |
| Social | validée 4/5, 83 % | 2 : (GRI 403-6) mis sur les aides financières aux étudiants et (GRI 403-4) sur le climat d'inclusion (ces publications sont reliées à PA-11 santé-sécurité) | 0 | 1 (les 45 sous-traitants sont bien dans PA-13) |
| Enseignement | validée 4/5, 100 % | 2 : description d'EN-7 (horticulture, véhicules électriques) recopiée pour EN-2 et EN-5 | 0 | 1 |
| **Total** | **8 validées, 0 à relire, 0 repli** | **24** | **1 (4 %)** | **7, dont 1 écartée par le code** |

**Lecture honnête de la comparaison (16 → 24 erreurs)**

| Type d'erreur | Avant | Après |
|---|---|---|
| Chiffres et marqueurs (chiffre détourné, phrase vidée, « % % », « d'ici » sans date…) | 9 | 3 (aucune valeur fausse : 2 textes de marqueur répétés, 1 année rattachée au mauvais objectif) |
| Forme (restes « (Ref) », phrase répétée, phrase ou liste orpheline) | 1 | 5 |
| Sens (contenu non sourcé, mal traduit, mauvais code GRI, sigle mal développé, matérialité) | 6 | 16 |

- Les corrections ont fait ce qu'elles visaient. Le code a retiré 13 phrases pendant cette série, dont « Environ {{ EN5 }} des étudiants », « revenu inférieur à {{ PA9 }} », « {{ PA2 }} points STARS sur {{ PA2_t0_0 }} », « de MWh » et « a identifié les thèmes matériels ». Aucun sigle n'est mal développé. Les 3 erreurs de chiffres restantes n'ont aucune valeur fausse.
- **Ce qui reste, c'est le sens.** Le modèle 8B invente ou déforme encore du contenu, surtout dans la section Environnement (8 erreurs à elle seule). Ce n'est pas lié aux corrections : d'une génération à l'autre, la même section peut être plus ou moins inventive.
- **Le juge 8B ne voit presque rien** (1 erreur sur 24). Il valide 8 sections sur 8. Une section « validée » veut dire « chiffres sûrs et forme contrôlée », pas « sens vérifié ». **Une relecture humaine reste nécessaire avant toute diffusion.**
- Trois défauts nouveaux viennent des retraits faits par le code ou des marqueurs complets :
  - le modèle écrit lui-même le début du marqueur (« un score STARS global de {{ STARS_score }} ») ;
  - les restes de renvoi « (Ref, Ref) » ;
  - une phrase ou une liste reste orpheline après un retrait.

  Le premier défaut s'est révélé massif : 27 phrases dans les 3 rapports, par exemple « 2,5 points STARS sur 3 au crédit PA-12, niveau élevé points STARS sur 2,5 points STARS sur 3… ». Il a donc été traité comme un **bug bloquant** et corrigé par le code, avec les restes « (Ref, Ref) » (`b4ac34e`, voir section 5). Le tableau ci-dessus décrit les textes avant ce nettoyage. Les deux autres défauts sont notés en section 6.

## 5. Corrections approuvées (« oui » du 5 octobre 2026)

| # | Correction | État | Commit | Tests |
|---|---|---|---|---|
| 0 | Annuler les sorties modifiées par les tests (`git checkout -- outputs`, `git clean -f outputs`) | fait (sections du test 3 sauvegardées hors du dépôt pour la comparaison) | — | — |
| 1 | **Marqueurs complets** (`{{ EN5 }}` → « 4,5 points STARS sur 8 au crédit EN-5, niveau intermédiaire ») + contrôle du contexte (après « d'ici/environ/inférieur à », avant « % » ou « étudiants », sans verbe de score, niveau contradictoire) + identifiants techniques refusés | fait | `05dd03f` | 100 passent (5 cas réels dans `tests/test_markers.py`) |
| 2 | **Années et % du texte STARS** extraits par le code (639 faits avec source crédit + ligne) et cités par marqueur ; phrases vidées (« d'ici . », « de MWh ») retirées ; « (Ref ) » retirés ; correction de la lecture des nombres à 4 chiffres (« 2028 » lu « 202 » + « 8 ») | fait | `5ecc1ef` | 106 passent (`tests/test_text_numbers.py`) |
| 3 | **Chat** : mots entiers sans accents (9 faux positifs + « emissions » sans accent + alias « tud » trouvé dans « étudiants ») ; biodiversité → IL-24 + OP-4 ; donnée absente dite par le code ; phrase « score de crédit = note Platinum » retirée | fait | `9cafd29` | 120 passent (`tests/test_chat.py`) |
| 4 | **Biodiversité dans les correspondances** : GRI 101 (2024) vérifiée sur globalreporting.org (remplace GRI 304 depuis le 1er janvier 2026) ; IL-24 → 101-4, 101-5, ESRS E4 ; OP-4 → 101-2 ; textes des crédits IL indexés (1 312 passages) ; IL-24 de TU Dublin marqué « Not Applicable » sur sa page STARS → « Non rapporté » | fait | `1c62a37` | 122 passent |
| 5 | **Lexique de 24 sigles** + règle de matérialité, donnés au rédacteur et au juge ; mauvais développés (« Services de l'État (SEC) ») et « a identifié les thèmes matériels » retirés par le code ; le juge lit les extraits avec leurs vrais nombres | fait | `88667de` | 125 passent (`tests/test_glossary.py`) |
| 6 | **Git** : un commit par correction ; envoi sur GitHub **à la fin seulement**, puis clone de vérification | fait : envoyé le 5 octobre ; clone neuf depuis GitHub = même HEAD, 120 fichiers suivis, `.env` absent | `4496377` | 132 passent dans le clone ; `esg.verify_univ 2026` : aucun écart |

Ajustements faits pendant la régénération de Dublin. Le garde-fou rejetait à tort des textes
corrects ; chaque cas réel est couvert par un test. Le code est **gelé** après `7e6d242`, avec une seule exception pour un bug
bloquant (`b4ac34e`).

| Ajustement | Cas réel | Commit |
|---|---|---|
| « % » écrit après un marqueur qui contient déjà « % » : le doublon est retiré, la phrase est gardée ; années acceptées après « plan stratégique » | thèmes matériels rejetés à tort | `ce8623e` |
| Années acceptées dans un nom de loi (« Act 2018 ») et après un mois (« février 2025 ») ; phrases identiques retirées | 7 phrases correctes retirées en gouvernance | `66b99dc` |
| Formulation interdite (« n'a pas fourni… ») : seule la phrase est retirée, plus tout le texte | section entière rejetée pour une phrase | `7e6d242` |
| Outil `esg.verify` : le pilier « ENV » était lu comme un crédit « EN-V » (chiffre déclaré absent à tort) | contrôle des 10 chiffres | `65e4773` |
| **Bug bloquant** : mots répétés autour d'un marqueur complet, retirés du texte rendu (suppression seule). Appliqué au rendu, donc les sections en cache sont corrigées sans relancer le LLM ; « (Ref, Ref) » est aussi retiré | 27 phrases illisibles dans les 3 rapports (Cork : toute la liste Environnement) | `b4ac34e` |


## 6. Notés, non appliqués

- ~~Défauts de forme restants~~ : corrigés le 6 octobre (section 9).
- **Contenu inventé ou mal rattaché** : seul un relecteur humain, ou un juge plus fort, peut le voir. Les
  24 sections des trois rapports ont été relues (sections 9 et 10). Piste pour la suite : un second juge qui
  vérifie chaque phrase contre l'extrait cité.

- **Second modèle Ollama comme juge** (amélioration future) : possible sur ce PC (153 Go de disque libre),
  mais pas deux modèles 8B chargés en même temps (1,7 Go de RAM libre pendant la génération) ; Ollama
  alternerait les chargements (≈ 20 à 40 s de plus par tentative). Candidats : `qwen2.5:7b` (≈ 4,7 Go)
  ou `qwen2.5:3b` (≈ 2 Go, tiendrait à côté de `llama3.1:8b`). Qualité à mesurer avec le même tableau.
- **GRI 102: Climate Change 2025** : en vigueur le **1er janvier 2027** (vérifié sur globalreporting.org) ;
  remplacera 305-1 à 305-5 et 201-2. GRI 305 reste valable pour un rapport publié en 2026.
- **Recommandations / application web** : absentes du projet ; à décider.

## 7. Comment reproduire

```powershell
.venv\Scripts\python -m pytest -q                      # tests automatiques
.venv\Scripts\python -m esg.validate                   # test 2
.venv\Scripts\python -m esg.verify 10                  # test 4 (tirage aléatoire, graine affichée)
.venv\Scripts\python -m esg.verify_univ 2026           # 10 chiffres par université (section 8)
.venv\Scripts\python -m esg.review                     # liste des corrections de relecture (section 9)
.venv\Scripts\python -m esg.pipeline --render-only      # re-rendre Word/PDF/HTML avec la relecture, sans LLM
.venv\Scripts\python -m esg.demo --juge                # test 5 (juge sur un texte faux)
.venv\Scripts\python -m esg.chat "Quel est le score biodiversité de Cork ?"   # test 6
.venv\Scripts\python -m esg.pipeline tudublin --no-cache --no-comparison --log outputs\logs\dublin.log   # test 3
```

## 8. Résultats finaux (5 octobre 2026, fin de la chaîne à 23 h 09)

Même code pour les 3 universités, une université à la fois : génération complète (`--no-cache`),
puis reprise des sections en texte de repli, puis synthèse comparative et rendu final. Journaux dans
`outputs/logs/` (`dublin_apres`, `dublin_replis`, `berkeley_apres`, `berkeley_replis`, `cork_apres`,
`cork_replis`, `rendu_final`, `rendu_corrige`).

**Sections**

| Université | Durée | Validées | À relire | Repli | Reprises | Phrases retirées par le code | Note du juge |
|---|---|---|---|---|---|---|---|
| TU Dublin | 104 min + 8,5 min | 8 / 8 | 0 | 0 | thèmes matériels (repli, puis validée à la reprise) | 13 | 4/5 sauf thèmes matériels 2/5 (violation écartée) |
| UC Berkeley | 100 min | 8 / 8 | 0 | 0 | aucune | 8 | 4/5 sauf stratégie 3/5 |
| University College Cork | 73,5 min + 9,3 min | 8 / 8 | 0 | 0 | enseignement (repli, puis validée à la reprise) | 5 | 4/5 partout |
| Synthèse comparative | 7 min | 1 / 1 | 0 | 0 | — | 1 | 4/5 |

Fidélité selon le juge : 100 % pour 19 sections sur 24, 83 % pour les 5 autres. Rappel
(section 4 bis) : « validée » veut dire chiffres sûrs et forme contrôlée, pas sens vérifié.

**10 chiffres au hasard par université** (`python -m esg.verify_univ 2026`, sortie complète dans
`outputs/verification_chiffres.md`). Chaque chiffre est comparé au CSV brut, sans passer par `facts.py`,
et doit figurer sur la ligne de son crédit ou de son pilier. S'y ajoutent 5 nombres « texte » par université
(années, %), comparés à leur ligne STARS d'origine.

| Université | Chiffres de score identiques au CSV | Nombres « texte » identiques à la source |
|---|---|---|
| UC Berkeley | 10 / 10 | 5 / 5 |
| University College Cork | 10 / 10 | 5 / 5 |
| TU Dublin | 10 / 10 | 5 / 5 |

Résultat : **aucun écart** (45 sur 45).

**Tests automatiques** : 132 passent (`pytest -q`).

## 9. Relecture hors pipeline et nettoyages de forme (6 octobre 2026)

**Qui a relu.** À la demande de Wiem Ben Hassine, **l'assistant Claude Code (une IA, pas une personne)** a
relu les sections contre les textes STARS et proposé les corrections. Chacune cite son passage, sa raison
et sa source. **Elles deviennent une relecture humaine une fois validées par Wiem** : lire
`outputs/relecture_humaine.md` et retirer ou modifier toute correction qui ne convient pas dans
`relecture/<université>.yaml`.

**Comment c'est appliqué.**
- Les corrections sont dans `relecture/<université>.yaml` (passage fautif, correction, raison, source STARS).
- `esg/review.py` les applique au rendu (`--render-only`), sans LLM.
- Le cache du modèle n'est pas modifié : on voit toujours ce que le modèle a écrit, et ce que la relecture a changé.
- Règles vérifiées par le code et par les tests (`tests/test_review.py`) :
  - chaque passage doit exister tel quel dans le texte validé ;
  - une correction ne contient **aucun chiffre tapé à la main** : les nombres viennent de `facts.csv` par marqueur (`{{ PA2_t0_9 }}` → 2050) et sont ajoutés à `provenance.csv` ;
  - si une section est régénérée, un passage introuvable est signalé au rendu (« ATTENTION relecture ») et le test échoue.
- L'annexe « Validation du rapport » de chaque rapport indique le nombre de corrections et qui les a proposées.

**Résultat.**

| Rapport | Sections relues | Erreurs | Corrigées par le code | Corrigées par la relecture | Erreurs en plus trouvées à cette relecture |
|---|---|---|---|---|---|
| TU Dublin | les 8 | 24 (tableau 4 bis) | 5 : marqueur répété (×2), « (Ref, Ref) », phrase répétée, « étaient : » sans liste | 19, en 22 corrections dans 7 sections | 5 : SEC présentées comme « ses » communautés ; « l'article » vide ; « collecte séparée » inventée ; « s'engage à verser un salaire décent » non sourcé ; « véhicules électriques » dans EN-7 |
| UC Berkeley | Environnement | 9 : énergie (imprécis) ; compensation (contresens « retraitement ») ; compostage « industriel » sur le campus ; « collecte séparée » ; « système » d'achats ; LEED-EBOM sous le mauvais crédit ; flotte répétée ; modes de déplacement (phrase vide) ; biodiversité (imprécis) | — | 9, en 11 corrections | — |
| University College Cork | Environnement | aucune affirmation inventée (le texte n'est qu'une liste de scores) ; 4 défauts de forme | 2 : marqueur répété (×14), « Voici la section rédigée : » | 2 : titre en double, titres vides | — |

En plus, à Dublin, les fonctions des membres étudiants sont maintenant écrites au neutre, puisque la source
ne donne pas leur genre. La liste complète est dans `outputs/relecture_humaine.md` (passage, raison, source,
correction).

**Nettoyages de forme ajoutés au code** (`esg/guard.py`, appliqués à la génération et au rendu ; suppression
seulement) :

| Règle | Ce qu'elle retire | Cas réels retirés dans les 25 textes |
|---|---|---|
| Phrase qui annonce une liste absente | une phrase finissant par « : » sans liste à la suite (une ligne en gras n'est pas une liste) | « …du corps de gouvernance étaient : » (Dublin), « Voici la section rédigée : » (Cork) |
| Phrase presque identique | au moins 90 % de ses mots porteurs de sens déjà écrits, **sans aucun chiffre, code de crédit ni marqueur nouveau**, donc deux crédits ou deux années différents ne sont jamais confondus | phrase sur le TU Act répétée (Dublin), « Ce rapport ne couvre pas… » répétant la phrase précédente (Berkeley), limite santé-sécurité répétée (Cork) |
| Fin de texte en liste | une liste en fin de section n'est plus prise pour une phrase coupée | la ligne de score IL-24 de Cork, qui avait disparu à un essai, est conservée |

**Contrôles après la relecture.**
- `pytest -q` : **140 tests passent**.
- Rendu sans LLM : aucun passage introuvable.
- `esg.verify_univ 2026` : **aucun écart** (45 sur 45).
- PDF et Word régénérés pour les 3 rapports et la synthèse comparative.

## 10. Relecture des autres sections de Berkeley et de Cork, et nouvelle section Environnement de Cork (6 octobre 2026)

Même méthode qu'en section 9 : chaque phrase relue contre les textes STARS, corrections écrites dans
`relecture/berkeley.yaml` et `relecture/cork.yaml` (passage fautif, raison, source avec numéro de ligne).
Elles ont été proposées par Claude Code et sont **à valider par Wiem**. La liste complète est dans
`outputs/relecture_humaine.md`.

**Erreurs trouvées et corrigées**

| Rapport | Sections | Erreurs | Exemples (source STARS) |
|---|---|---|---|
| UC Berkeley | les 7 hors Environnement | 23 (+ 1 coquille) | **42,8 % présenté comme « salaire minimum local »**, alors que c'est le taux composite des avantages sociaux, CBR (PA-13, l. 2, erreur signalée) ; « la proportion d'étudiants Pell… est de 2021 » (une année prise pour une proportion, PA-9) ; « Académie de la durabilité » inventée (Sénat académique, PA-3) ; plan stratégique du centre étudiant SERC présenté comme celui de l'université (PA-2, l. 8) ; « congé parental » pour *Family and Medical Leave* (PA-12) ; noms de contacts présentés comme résultats (PA-8, PA-10) ; EN-1 et EN-3 sans rapport avec le crédit |
| UC Berkeley | Environnement (section 9) | 9 | déjà corrigées |
| University College Cork | les 6 hors Environnement | 16 (+ 1 coquille) | **neutralité carbone « d'ici 2030 »** au lieu de 2040 (PA-1, l. 3) ; « élaboré **en référence aux normes GRI** », inventé (PA-2) ; objectif de 51 % présenté comme un plan propre alors que c'est l'objectif du gouvernement, que le plan veut dépasser (PA-2, l. 13) ; « plan » traduit par « stratégie » (×4) ; engagements PRI présentés comme des politiques en place (PA-4) |
| University College Cork | Environnement (nouveau texte) | 4 (+ 1 titre en double) | « pompier à chaleur » au lieu de pompe à chaleur (OP-3) ; score « dû à » la méthode de calcul, lien inventé (OP-6) ; « Nous » recopié de la source ; 5 % mal compris (part moyenne des points d'évaluation des appels d'offres, OP-9) |

Corrigé aussi par le code, sans relecture : les marqueurs répétés (8 phrases à Berkeley, et à Cork les 10
lignes de l'enseignement sous la forme « …niveau maximal au crédit AC-1 Offre de cours…, niveau maximal »)
et les phrases presque identiques.

**Section Environnement de Cork régénérée (LLM)**

| Série (graine) | Résultat |
|---|---|
| 0 (`--no-cache`, même graine qu'avant) | **même texte** qu'avant, une liste de scores : avec la même graine, le modèle réécrit exactement la même chose |
| 1 | **repli** : les 2 versions ont été refusées par le garde-fou (scores sans verbe, « 0 » tapés par le modèle, 10 niveaux faux, par exemple OP-9 « élevé » au lieu de faible) |
| 2 | **validée** (juge 4/5, fidélité 100 %), avec un vrai texte : 6 crédits sur 14 décrits avec leurs sources (le tableau du code donne les 14 scores) |

Le juge n'a vu aucune des 4 erreurs du nouveau texte ; sa seule « violation » était fausse. La conclusion de
la section 4 bis tient toujours : le juge valide, la relecture corrige le sens.

**Modifications du code**
- `--no-cache` change maintenant de graine quand une version existe déjà (`esg/generate.py`). Sinon, régénérer ne sert à rien.
- Répétition du libellé du crédit après un marqueur, retirée seulement si le même niveau suit (`esg/guard.py`, test du cas réel de Cork).
- Relecture : « scopes 1 et 2 » et « ISO 14064-1 » sont acceptés comme des noms, pas comme des chiffres tapés à la main (`esg/review.py`).

**Totaux de la relecture (3 rapports, 24 sections)**

| Rapport | Corrections appliquées | Sections |
|---|---|---|
| TU Dublin | 22 | 7 (l'organisation n'avait qu'une erreur, corrigée par le code) |
| UC Berkeley | 35 | 8 |
| University College Cork | 22 | 7 (l'enseignement n'avait que des marqueurs répétés, corrigés par le code) |

**Contrôles**
- `pytest -q` : **142 tests passent**, dont un sur l'erreur du 42,8 % et un sur le libellé répété de Cork.
- Rendu sans LLM : aucun passage introuvable.
- `esg.verify_univ 2026` : **aucun écart** (45 sur 45).
- Word, PDF et HTML régénérés.

## 11. Qualité du texte : nouvelle génération des trois rapports (7 octobre 2026)

**Demande de Wiem.** Rendre le texte des rapports plus concret (moins de listes de scores et de formules
creuses), puis régénérer les trois universités le même jour. Pour chaque université : comparer l'ancien et le
nouveau texte, et refaire la relecture avec la source STARS de chaque correction. Le soir, Wiem choisit
l'ancien ou le nouveau rapport, université par université. Si une génération échoue ou n'est pas meilleure,
l'ancien est conservé.

**Langue.** Les rapports restent en **français**. Une version anglaise est une perspective (section
« Perspectives » ci-dessous), pas un livrable de ce stage.

**Ce qui a changé (branche `rapport-qualite`, fusionnée dans `main`)**

| Étape | Changement | LLM ? |
|---|---|---|
| a) | Paragraphe « Points forts et points à améliorer » **écrit par le code** à partir des scores : au moins 75 % des points = point fort ; moins de 40 % = à améliorer ; entre les deux = partiellement atteint. Annexe de validation plus claire (« deux essais au plus », codes GRI cités contre publications GRI avec données). Style : « l'université » en minuscule, formules creuses retirées au rendu (`esg/style.py`). | non |
| b) | Rédacteur : 2 à 3 extraits STARS par crédit (au lieu des extraits les plus proches, tous crédits mélangés), questions du formulaire STARS et lignes d'URL retirées des extraits, contexte de 6 144 jetons. Consignes : une ou deux phrases concrètes par crédit, **pas de liste de scores**, pas de formule promotionnelle. Contrôles : une section qui n'est qu'une liste de scores est renvoyée au modèle (`judge.score_list`) ; une phrase creuse est retirée (`guard`). | — |
| c) | Génération des 3 universités, en deux passes : passe 1 complète (`--no-cache`), passe 2 pour les sections restées en texte de repli. | oui |
| d) | Pour chaque université : document de comparaison `comparaison/comparaison_<université>.md` et nouvelle relecture `relecture/<université>.yaml`. | non |
| — | Assistant : « régénère les rapports… » lance les deux passes, avec un journal par passe dans `outputs/logs/` ; une faute de frappe sur le verbe (« genenre le rapport de dublin », vue par Wiem) donne le rendu depuis le cache, jamais Ollama. | non |

**Génération (passe 1 : 8 h 44 → 13 h 58, 313,6 min)**

| Université | Durée | Validées | À relire | Repli | Phrases retirées par le code | Essais refusés (garde-fou / juge) |
|---|---|---|---|---|---|---|
| University College Cork | 128 min | 6 | 2 (gouvernance, enseignement) | 0 | 7 | 2 / 3 |
| UC Berkeley | 89 min | 7 | 1 (social) | 0 | 8 | 1 / 1 |
| TU Dublin | 90 min | 7 | 0 | 1 (enseignement) | 5 | 2 / 2 |

Les nouveaux contrôles ont servi : la liste de scores a été renvoyée une fois (Berkeley, social) ; trois essais
ont été refusés parce que le modèle citait des codes GRI dans la section « hors GRI » (enseignement).

**Passe 2.** Elle s'est arrêtée à 14 h 11, pendant le rendu PDF de Berkeley : Edge sans fenêtre n'a pas répondu
en 180 s. Cause : le profil Edge réservé au pipeline (`data/processed/edge_profile`) était bloqué (Edge rendait
la main sans écrire de PDF) ; avec un profil neuf, le PDF sort en 5 s. Le profil bloqué a été mis de côté et la
passe 2 relancée pour TU Dublin à 14 h 22 (27,6 min) : l'enseignement de TU Dublin est **de nouveau en repli**
(juge 2/5 et fidélité 50 %, puis codes GRI cités). Le rapport contient donc pour cette section le texte de repli
du code (liste des scores).

**Comparaison ancien / nouveau** (détail section par section dans `comparaison/`)

| Université | Corrections de relecture (ancien → nouveau) | Nouveau meilleur | Ancien meilleur | Recommandation (Claude Code, à décider par Wiem) |
|---|---|---|---|---|
| University College Cork | 27 → 40 | social, enseignement (nettement) ; stratégie, environnement (un peu) | thèmes matériels, gouvernance | **nouveau** |
| UC Berkeley | 35 → 34 | parties prenantes (un peu) | environnement, social, enseignement | **ancien** |
| TU Dublin | 22 → 24 (+ enseignement en repli) | environnement (un peu) | thèmes matériels, gouvernance, parties prenantes, social, enseignement | **ancien** |

Le nouveau texte de Berkeley et de TU Dublin n'est exact qu'après une relecture qui en remplace une grande partie ;
pour Cork, le gain sur social et enseignement est net.

**Constats (limites à retenir)**

1. **Plus d'extraits ne suffit pas.** Avec `llama3.1:8b` sur processeur, le texte n'est meilleur que pour Cork.
2. **Extraits mal choisis.** Pour les thèmes matériels de Cork, la recherche a donné au modèle trois fois la phrase
   d'introduction de la liste des objectifs PA-2, et aucun objectif : le modèle a inventé les objectifs. À TU
   Dublin, des lignes « This credit was marked as Not Applicable » et « Total adjusted… » ont aussi été données
   comme extraits.
3. **Le juge ne voit pas un texte générique.** L'enseignement de Berkeley, sans un seul fait ni score
   (« L'université a mis en place des programmes pour… »), a reçu 4/5 et 100 % de fidélité ; les « thèmes
   matériels déclarés » inventés de TU Dublin ont reçu 4/5. Une phrase vague n'est pas une affirmation fausse.
4. **Le contrôle des formules creuses** repose sur une liste fixe de formules ; il ne reconnaît pas les
   tournures génériques de Berkeley.
5. **Nouveaux types d'erreurs** : pourcentages inversés (Cork, 21 % et 54 % des appels d'offres) ; une année
   devenue une durée (« formation de 2024 heures ») ; faits rangés sous le mauvais titre et le mauvais code GRI
   (Berkeley et TU Dublin, social) ; « thèmes matériels déclarés » inventés (TU Dublin).
6. **La relecture reste indispensable** : 98 corrections proposées pour les nouveaux textes, chacune avec sa ligne STARS. La validation
   automatique (règle « aucun chiffre tapé à la main ») a aussi bloqué une correction qui contenait « bâtiment
   neuf » (« neuf » est lu comme un nombre en lettres) : corrigé en « nouveau ».

**Perspectives**
- **Rapport en anglais** : le modèle écrit mieux en anglais et les sources STARS sont en anglais (moins
  d'erreurs de traduction : « Académie du Sénat », « committment »). Il faudrait traduire les consignes, les
  libellés des marqueurs et les règles du garde-fou, puis refaire la relecture.
- Choisir les extraits par crédit en écartant les lignes d'en-tête de liste et les lignes « Not Applicable ».
- Donner au juge une règle « une phrase sans fait précis est une violation ».
- Un modèle plus grand ou un GPU (le 8B sur CPU écrit 2 à 4 jetons par seconde).

**Choix final de Wiem (7 octobre, appliqué dans `main`)**

| Université | Version livrée | Texte du modèle | Sections validées | Relecture |
|---|---|---|---|---|
| University College Cork | **nouvelle** (7 octobre) | génération du 7 octobre | 6 / 8 (2 à relire : gouvernance, enseignement) | 40 corrections dans 8 sections |
| UC Berkeley | **ancienne** (6 octobre) | génération du 5 octobre | 8 / 8 | 35 corrections dans 8 sections |
| TU Dublin | **ancienne** (6 octobre) | génération du 5 octobre (thèmes matériels rejoués) | 8 / 8 | 22 corrections dans 7 sections |
| **Total** | | | **22 / 24** | **97 corrections** |

L'ancien texte et l'ancienne relecture de Berkeley et de TU Dublin ont été repris du commit `9992123`
(`git checkout 9992123 -- outputs/cache/<université> relecture/<université>.yaml`), puis les rapports ont été
re-rendus sans LLM. Les nouveaux textes de Berkeley et de TU Dublin, et leur relecture (34 et 24 corrections),
restent consultables dans l'historique (commit `017a9e6`) et dans `comparaison/`.

**Chiffres finaux (sur `main`, après le choix)**
- `pytest -q` : **179 tests passent**, dont 4 nouveaux cas pour l'assistant (faute de frappe sur le verbe ;
  questions sur le « genre » qui restent des questions normales). Ils passaient aussi avec les nouveaux textes des
  trois universités : ils vérifient le défaut, pas une phrase exacte.
- Rendu sans LLM : aucun passage de relecture introuvable ; Word, PDF et HTML régénérés pour les 3 rapports et la
  synthèse comparative.
- `esg.verify_univ 2026` : **aucun écart** (45 sur 45 : 10 chiffres de score et 5 nombres « texte » par
  université ; sortie dans `outputs/verification_chiffres.md`).
- Assistant : « génère le rapport de Cork » et « genenre le rapport de dublin » rendent le rapport depuis le
  cache (sans Ollama) et ouvrent le PDF.
