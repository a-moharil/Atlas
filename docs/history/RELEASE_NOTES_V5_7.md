# Atlas v5.7: geopolitics reel and a better floating player

## Geopolitics reel (Live TV and video)

- Plays recent news videos (last 24 hours) from international broadcasters one after another. New channels are Al Jazeera English, France 24 English, Sky News, Associated Press, TRT World, CNA, Euronews English, NHK World-Japan and ABC News (Australia). The existing BBC News, DW, Reuters and WION channels are also included. The list is under `geo_reel` in `source_registry.json`.
- **News only:** shorts, sport, entertainment, lifestyle and similar are left out. **Geopolitics** (the default) also requires a title about conflict, diplomacy, sanctions, summits, elections or the countries and leaders involved. **All news** drops that requirement.
- Channels take turns (newest first within each), so one broadcaster can't fill the reel.
- **Stop circulating / Resume circulating**, Previous, Next, and an *Up next* list with Remove. *Next video after*: 1, 3 or 5 minutes, or when the video ends. The countdown pauses while the video is paused. Settings are remembered in the browser.
- Videos start muted (browsers block autoplay with sound). After you unmute, later videos stay unmuted, because the reel switches videos inside the same player.
- *Open in floating player* moves the current video to the floating player and stops circulating.
- The footer says what was left out (not news, not geopolitics, waiting for YouTube's check, won't play) and which channels couldn't be fetched.
- Reel-only uploads stay out of the desks, story groups and the *Recent broadcaster uploads* rail.
- `tools/check_geo_channels.py` checks every reel channel from your computer.

## Floating player

- **Move:** drag the title bar, or use the arrow keys when the bar has focus. Embedded players are switched off during a drag so they can't swallow the pointer. The position is remembered.
- **Resize** from the bottom-right corner.
- **Maximise:** button or double-click the title bar; Esc restores.
- **Full screen:** button; Esc or the same button exits.
- *Open on YouTube* link in the caption.

## "This video is unavailable"

- Atlas now listens to YouTube's player (IFrame API messages), so it knows when a video won't play.
- **Live streams:** a "verified live" video can end between checks. Atlas asks for a fresh live check and switches to the channel's current live stream. If that also fails, the player explains why and offers *Watch on YouTube*.
- **Uploads:** the video is marked as not playable in this browser and isn't offered again for a week. YouTube's oEmbed check can't see region blocks, so the browser's answer wins for that week.
- New endpoint: `POST /api/video/player-error {video_id, code}`.

## API

- `GET /api/geo-reel?hours=24&scope=geo|news` returns `{videos, counts, channels, hours, scope}`.

## Tests

`tests/test_v57_reel.py` covers classification, time window, filters, channel rotation, duplicates, player errors, the recheck window, the endpoints, and keeping reel uploads out of the desks. Full suite: 141 tests pass on Python 3.13. On 3.9 everything passes except `test_v51_lm`, which needs numpy (unchanged).
