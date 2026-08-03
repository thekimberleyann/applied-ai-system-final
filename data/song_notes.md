# Song Notes (retrieval corpus)

This file is the knowledge source for VibeFinder's RAG explanation layer. Each song
in data/songs.csv has one factual note below, keyed by its exact title as an H2
header. The retriever (src/retriever.py) parses this file into a title -> note
lookup, and the LLM explainer is allowed to ground its wording ONLY in the note it
retrieves for a given song.

Every note is written to stay consistent with that song's catalog attributes
(genre, mood, energy on a 0.0-1.0 scale, and tempo in BPM). Nothing here invents
chart history, awards, or streaming numbers -- only the sound and the setting.

## Sunshine Pop
A bright, upbeat pop track by The Brights. High energy at 0.85 and a brisk 124 BPM
give it a sing-along, feel-good lift. Best for a happy, high-spirits moment -- a
morning playlist, a sunny drive, or anything meant to raise the mood.

## Midnight Drive
A synthwave cut by Neon Roads with glowing retro synths and a steady 118 BPM pulse.
At 0.75 energy it drives without racing, so it suits an energetic-but-focused late
night mood -- headlights, highways, and neon.

## Lofi Rain
A calm lofi beat by Study Cat, low energy at 0.30 and a slow 72 BPM. Soft, hazy,
and unhurried, it is built for a chill background -- studying, reading, or winding
down without distraction.

## Heavy Riff
A hard-driving rock track by Iron Pulse, near the top of the scale at 0.95 energy
and a fast 140 BPM. Loud guitars and an intense mood make it a workout-or-adrenaline
pick, not background music.

## Acoustic Morning
A gentle acoustic song by Jane Willow, low energy at 0.35 and an easy 90 BPM. Warm,
calm, and stripped back, it fits a slow morning, a coffee, or a quiet reset.

## Dance All Night
A high-octane EDM track by DJ Vortex, 0.90 energy and a club-standard 128 BPM. Built
for movement and an energetic mood -- a party, a dance floor, or a run.

## Blue Notes
A smooth jazz number by Miles Ahead, mid-low energy at 0.45 and a relaxed 100 BPM.
Mellow and understated, it works as easy-listening for dinner, late evenings, or
quiet focus.

## Summer Anthem
An upbeat pop anthem by Coast Kids, high energy at 0.80 and a danceable 120 BPM.
Happy and open-air, it fits summer playlists, road trips, and good-mood moments.

## Rainy Day Blues
A slow blues song by Sad Sax, low-mid energy at 0.40 and an unhurried 85 BPM.
Melancholy and saxophone-led, it leans into a sad, reflective mood on a grey day.

## Power Up
An electronic track by Arcade Heroes, high energy at 0.88 and a driving 130 BPM.
Bright, arcade-flavored, and energetic, it suits gaming, focus sprints, or a
pick-me-up.

## Golden Hour
A hip-hop track by Vega Verse, mid energy at 0.65 and a laid-back 95 BPM. Warm and
nostalgic in mood, it fits an easy evening, a look-back playlist, or a mellow hang.

## Crown Season
A hip-hop track by Vega Verse, high energy at 0.85 and a hard 102 BPM. Confident and
aggressive in mood, it is a hype pick -- gym, game day, or a bold entrance.

## Backroad Sunset
A country song by Dusty Wheels, mid energy at 0.55 and a steady 98 BPM. Nostalgic
and open-road in feel, it suits a drive at dusk or a wistful, easygoing mood.

## Moonlight Redux
A classical piece by the A. Keys Trio, the lowest energy in the catalog at 0.25 and
a slow 60 BPM. Calm and delicate, it fits deep focus, reading, or a quiet night.

## Velvet Touch
An R&B song by Silk Avenue, mid energy at 0.50 and a smooth 92 BPM. Romantic and
silky, it suits a slow evening, a date, or an intimate mood.

## Iron Fury
A metal track by Bladewright, the highest energy in the catalog at 0.98 and a
blistering 150 BPM. Heavy and aggressive, it is pure intensity -- lifting, sprinting,
or blowing off steam.

## Island Time
A reggae song by Palm Groove, mid energy at 0.55 and a loose 76 BPM. Chill and
sun-warmed, it fits a laid-back afternoon, a hammock, or an easygoing mood.

## Wandering Roads
A folk song by Hazel Pine, low-mid energy at 0.40 and a gentle 88 BPM. Acoustic and
nostalgic, it suits a quiet reflective walk or a wistful, low-key moment.

## Soul Fire
A soul song by Ruby Grand, mid energy at 0.60 and a steady 100 BPM. Warm and
romantic with a smoky vocal feel, it fits an intimate evening or a heartfelt mood.

## Cloudscape
A dreampop track by Slow Halo, mid-low energy at 0.45 and an easy 105 BPM. Hazy,
reverb-washed, and dreamy, it suits a floaty, introspective mood -- late night or a
slow drift.
