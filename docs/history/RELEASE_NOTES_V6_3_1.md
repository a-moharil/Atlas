# Sanjaya v6.3.1 · Silent refresh on the Elections page

- The Elections page no longer redraws abruptly when results are re-read. Background checks run quietly; the page is redrawn in place only when something actually changed, keeping the scroll position, selected seat, coalition and map mode.
- Download progress for the results pack updates the bar without redrawing the page.
