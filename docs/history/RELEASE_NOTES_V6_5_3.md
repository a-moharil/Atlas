# Sanjaya v6.5.3 · US maps that change with the year, one meaning per colour

## What was wrong
- Each Senate year only changes about a third of the seats. The other two-thirds were drawn in faded party colours, so the map and seat chart looked almost the same from year to year even though the numbers changed.
- "Faded" also meant a narrow margin, and in v6.5.1 an uncalled race, so the colours were ambiguous.
- Angus King's 2012 win was filed as "Other" rather than "Independent", which put a stray grey seat in the Senate from 2012 to 2016.

## What changed
- **Colours:**
  - Solid party colour means won, with three tints for the margin (under 5, 5 to 15, over 15 points).
  - Party stripes with a dashed edge mean not yet called, shaded toward the leader.
  - Slate grey means no race for that office there that year.
- **Senate and governor maps** have two views. *<year> races* colours only that year's races. *Whole Senate / All governors after it* shows every seat, with split Senate delegations striped in both party colours.
- **Seat chart:** seats won that year are solid; seats elected earlier are hollow rings; uncalled seats are striped.
- **Net change** against the previous election appears at the top ("R +4 since 2022") and beside each party.
- **Party codes:** winners on their own ballot line (King 2012, "Connecticut for Lieberman") count as independents. The results pack version is now 2, so the page asks to rebuild it; the files you already downloaded are reused, so it takes seconds.

## Includes v6.5.2
Associated Press as a source with your own key, and lean shading.

## Tests
2 new tests: the King fix, net change, years differing, and the colour rules. Full suite: 259 tests.
