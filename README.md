# IDFM pour Home Assistant

Intégration personnalisée pour Home Assistant affichant :
- l'**état du trafic** des lignes IDFM (métro, RER/Transilien, tram, bus) ;
- les **prochains départs** (temps réel) pour une station donnée.

Fournit aussi deux cartes Lovelace prêtes à l'emploi :
- `idfm-traffic-card` : picto de ligne, nom de ligne, message d'état du trafic.
- `idfm-departures-card` : nom de la gare/station, 3 prochains départs au format `1min`, `4min`, `8min`.

## Installation

### Via HACS
1. HACS → Intégrations → menu ⋮ → *Dépôts personnalisés* → ajoutez l'URL de ce dépôt (catégorie *Integration*).
2. Installez "IDFM - Ile-de-France Mobilités", puis redémarrez Home Assistant.

### Manuelle
Copiez le dossier `custom_components/idfm` dans `<config>/custom_components/idfm`, puis redémarrez Home Assistant.

Les deux cartes Lovelace (`idfm-traffic-card.js`, `idfm-departures-card.js`) sont enregistrées
automatiquement au démarrage — aucune ressource Lovelace à ajouter manuellement.

## Clé API

Créez un compte gratuit sur [prim.iledefrance-mobilites.fr](https://prim.iledefrance-mobilites.fr),
puis générez une clé API dans votre espace (elle donne accès aux API temps réel et trafic).

## Configuration

Paramètres → Appareils et services → Ajouter une intégration → "IDFM".

Ajoutez l'intégration **une fois par élément à suivre** :
- une clé API (réutilisée par défaut si vous en avez déjà configuré une) ;
- le type de suivi : *État du trafic d'une ligne* ou *Prochains départs d'une station* ;
- le mode de transport, puis la ligne ;
- pour les départs : la station, puis éventuellement une direction/destination précise.

Chaque ajout crée une entité `sensor.*` :
- **Trafic** : état = `normal` / `info` / `perturbe` / `interrompu`, avec les attributs
  `line_name`, `short_name`, `color`, `text_color`, `message`, `title`, `effect`,
  `severity`. Les perturbations proviennent de l'API Navitia *line_reports* de PRIM :
  `interrompu` = effet `NO_SERVICE`, `perturbe` = service réduit, retards importants,
  déviation ou arrêt déplacé, `info` = autre message actif. Seules les perturbations
  dont une période d'application est en cours comptent (des travaux de nuit ne passent
  la ligne en `interrompu` que pendant la nuit).
- **Départs** : état = minutes avant le prochain départ, avec l'attribut `departures`
  (liste des 3 prochains passages : `destination`, `minutes`, `formatted`).

## Cartes du tableau de bord

### Trafic

```yaml
type: custom:idfm-traffic-card
title: Trafic
entities:
  - sensor.rer_a
  - sensor.metro_1
```

### Prochains départs

```yaml
type: custom:idfm-departures-card
title: Prochains départs
entities:
  - sensor.gare_de_lyon_rer_a
```

Chaque carte accepte aussi un simple `entity: sensor.xxx` pour une seule ligne/station.

## Notes

- Le trafic est rafraîchi toutes les 3 minutes, plus lentement si beaucoup de lignes
  partagent le token (l'intervalle est calculé pour tenir dans le quota). Les départs sont rafraîchis toutes les
  minutes **uniquement quand une carte `idfm-departures-card` les affiche à l'écran**
  (onglet visible et carte dans la zone affichée) ; sinon aucune requête n'est faite.
  Pour une automatisation, forcez une mise à jour avec `homeassistant.update_entity`.
- Les quotas PRIM (par token, sur 24h glissantes) sont comptés localement et ne sont
  jamais dépassés : 950 requêtes de départs et 950 de trafic par défaut
  (`QUOTA_*` dans `const.py`, à relever si PRIM vous a accordé plus). Une fois le quota
  atteint, les dernières données sont conservées et les minutes continuent de défiler.
- Les couleurs et noms courts de ligne proviennent du jeu de données ouvert IDFM
  *Référentiel des lignes* (mis en cache après le premier appel).
- Cette intégration n'est pas affiliée à Île-de-France Mobilités.
