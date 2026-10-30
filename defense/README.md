# Astro Adventure

[한국어](README.ko.md)

A portrait wave-defense game prototype that runs straight in the browser. Everything lives in a single `index.html`.

## Rules
- Your side is on the left (18 slots for the Astro Friends). Alien bugs charge in from the right.
- **Summon**: spend coins to get a random unit from 6 types. Each summon costs 2 more than the last.
  - Grade odds: Common 72% · Rare 22% · Epic 5.5% · Legendary 0.5%
- **Merge**: drag a unit onto another of the same type and grade to make the next grade.
- **Sell**: drag a unit onto the Sell zone at the bottom left to get coins back.
- **Rounds**: a new round starts every 30 seconds. There are 30 rounds.
- **Bosses**: mini bosses at rounds 10 and 20, the final boss at round 30. Defeat the final boss within 30 seconds to win.
- Enemies attack the wall. If the wall's HP hits 0, you lose.
- **Level-up cards**: kills drop XP gems. When the XP bar fills, pick 1 of 3 cards (all damage, attack speed, crit, a unit type's drill, and more). One card is marked as recommended for your squad. You get 3 rerolls per run.
- **Legendary reveal**: summoning or merging a legendary unit plays a full-screen reveal.
- **Upgrades**: each run pays out gold (more for later rounds and a win). Spend it on permanent upgrades from the title or results screen: Attack, Wall HP, Armor, Starting Coins, Lucky Summons, Fast Learner. Progress is saved in this browser.

## Units
The units are the Astro Friends. A badge in the corner of each slot shows the role.

| Friend | Animal | Role |
|---|---|---|
| Cheddar | Cat | Rifle: rapid fire at the closest enemy |
| Cotton | Rabbit | Sniper: full-map range, targets the enemy with the most HP |
| Maple | Fox | Flame: short-range area damage (place near the wall) |
| Chestnut | Bear | Mortar: shells deal area damage |
| Mochi | Panda | Frost: slows the enemies it hits |
| Zippy | Hamster | Tesla: lightning chains between enemies |

Five friends are cut from the character sheet. Zippy is drawn in code until real art exists.

Range is how far a unit reaches to the right of its slot, so short-range units belong in the column next to the wall.

## Controls
- Touch/mouse: Summon button, drag units (move, merge, sell), tap a unit (info and range)
- Keyboard: Space/Enter to summon, Esc/P to pause, 1/2/3 to pick a level-up card
- The `EN`/`한` button at the top right switches between English and Korean (English by default)

## Balance notes
With no permanent upgrades, a bot that merges everything, spends leftover coins on summons and takes the recommended card (with no placement strategy) won 3 of 8 runs; the other 5 ended at rounds 29 and 30. Placing units by range and buying upgrades gives you an edge.
Tune the numbers near the top of `index.html`: `TYPES`, `GRADES`, `MON`, `BOSS_HP`, `hpBase`, `drawCost`, `CARDS`, `META`. On-screen text is in the `STR` table.
