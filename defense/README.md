# Astro Adventure

[한국어](README.ko.md)

A portrait roaming survival game prototype that runs straight in the browser. Everything lives in a single `index.html`.

## Rules
- You roam a map 2 screens wide and 2 screens tall, with a few moon rocks to dodge around. Alien bugs come from every side and chase your leader.
- **Leader and squad**: the highest-grade friend in the squad leads; the rest follow in a line. Only the leader can be hit. A touch costs HP, then the leader blinks for a moment. If the leader's HP hits 0, you lose.
- **Rounds**: each round lasts 30 seconds, 30 rounds in total. When the time is up, leftover bugs leave, gems on the ground are collected, and the leader heals 30% of max HP.
- **Prep screen** (between rounds): spend coins to summon random friends, drag them between the 6 squad slots and the 12-slot bench, merge two of the same type and grade into the next grade, sell what you don't need, then press GO.
  - Grade odds: Common 72% · Rare 22% · Epic 5.5% · Legendary 0.5%. Each summon costs 2 more than the last.
- **Encircling waves**: from round 5, a ring of bugs closes in twice a round. Slip through a gap.
- **Bosses**: mini bosses at rounds 10 and 20, the final boss at round 30. Defeat the final boss within 30 seconds to win. An arrow on the screen edge points to an off-screen boss.
- **Level-up cards**: kills drop XP gems. Walk close to pick them up (Strong Magnet widens the range). A full XP bar opens a pick-1-of-3 card screen with a recommended card and 3 rerolls per run.
- **Upgrades**: each run pays out gold for permanent upgrades from the title or results screen: Attack, Leader HP, Armor, Starting Coins, Lucky Summons, Fast Learner. Progress is saved in this browser.

## Units
The units are the Astro Friends. A badge in the corner of each slot shows the role.

| Friend | Animal | Role |
|---|---|---|
| Cheddar | Cat | Rifle: rapid fire at the closest enemy |
| Cotton | Rabbit | Sniper: longest range, targets the enemy with the most HP |
| Maple | Fox | Flame: short-range area damage |
| Chestnut | Bear | Mortar: shells deal area damage |
| Mochi | Panda | Frost: slows the enemies it hits |
| Zippy | Hamster | Tesla: lightning chains between enemies |

Five friends are cut from the character sheet. Zippy is drawn in code until real art exists.

Range is the attack radius around each friend. Maple (flame) has the shortest reach, Cotton (sniper) the longest.

## Controls
- Battle: touch anywhere on the map and drag to steer the leader (virtual joystick). Arrow keys or WASD also work.
- Prep screen: drag friends to move, merge or sell; tap a friend for details.
- Keyboard: Space to summon and Enter for GO on the prep screen, Esc/P to pause, 1/2/3 to pick a level-up card
- The `EN`/`한` button at the top right switches between English and Korean (English by default)

## Balance notes
With no permanent upgrades, a bot that dodges by pushing away from nearby bugs, merges everything, puts its six best friends in the squad and takes the recommended card won 2 of 5 runs; all 5 reached the final boss at round 30. People dodge worse than the bot, so expect the middle rounds to bite harder.
Tune the numbers near the top of `index.html`: `TYPES`, `GRADES`, `MON`, `BOSS_HP`, `hpBase`, `drawCost`, `CARDS`, `META`, and the map and movement constants (`WORLD_W`, `LEADER_SPD`, `PICK_R`). On-screen text is in the `STR` table.
