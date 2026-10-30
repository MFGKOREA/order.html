# Kitty Defense

[한국어](README.ko.md)

A portrait wave-defense game prototype that runs straight in the browser. Everything lives in a single `index.html`.

## Rules
- Your side is on the left (18 slots for cat mercenaries). Alien bugs charge in from the right.
- **Summon**: spend coins to get a random unit from 6 types. Each summon costs 2 more than the last.
  - Grade odds: Common 72% · Rare 22% · Epic 5.5% · Legendary 0.5%
- **Merge**: drag a unit onto another of the same type and grade to make the next grade.
- **Sell**: drag a unit onto the Sell zone at the bottom left to get coins back.
- **Rounds**: a new round starts every 30 seconds. There are 30 rounds.
- **Bosses**: mini bosses at rounds 10 and 20, the final boss at round 30. Defeat the final boss within 30 seconds to win.
- Enemies attack the wall. If the wall's HP hits 0, you lose.

## Units
| Unit | Role |
|---|---|
| Rifle Cat | Rapid fire at the closest enemy |
| Sniper Cat | Full-map range, targets the enemy with the most HP |
| Flame Cat | Short-range area damage (place near the wall) |
| Mortar Cat | Shells deal area damage |
| Frost Cat | Slows the enemies it hits |
| Tesla Cat | Lightning chains between enemies |

Range is how far a unit reaches to the right of its slot, so short-range units belong in the column next to the wall.

## Controls
- Touch/mouse: Summon button, drag units (move, merge, sell), tap a unit (info and range)
- Keyboard: Space/Enter to summon, Esc/P to pause
- The `EN`/`한` button at the top right switches between English and Korean (English by default)

## Balance notes
Over 8 runs, a bot that merges everything and spends leftover coins on summons (with no placement strategy) won 3 and lost the other 5 between rounds 27 and 30. Placing units by range gives you an edge.
Tune the numbers near the top of `index.html`: `TYPES`, `GRADES`, `MON`, `BOSS_HP`, `hpBase`, `drawCost`. On-screen text is in the `STR` table.
