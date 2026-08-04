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

## Confetti Skies
A bright, major-key pop tune that lands squarely in happy territory, with a punchy 0.72 energy and a danceable 116 BPM. Play it for celebrations, getting-ready playlists, or any moment that needs an easy lift.

## Chrome Sunset
A synthwave piece that trades adrenaline for atmosphere, sitting in a dreamy mood at a mid 0.60 energy and an unhurried 100 BPM. Its neon-lit synth washes suit late-night drives and reflective, retro-tinged moments.

## Study Fog
A lofi track built for the background, mellow and low-key at 0.28 energy over a slow 74 BPM. The soft, hazy loop is made for studying, reading, or winding down without distraction.

## Concrete Anthem
A hard-driving rock song with an intense mood, high 0.90 energy, and a fast 138 BPM. The heavy guitars and forward momentum fit workouts, hype moments, and anything that needs a jolt.

## Static Rebellion
An energetic rock number pushing 0.85 energy at a brisk 132 BPM. Its driving riffs and steady drive make it a solid pick for a road trip or a rising-energy playlist.

## Candle Hours
A quiet acoustic piece in a calm mood, gentle at 0.32 energy over a slow 82 BPM. Sparse guitar and a soft touch make it well suited to evenings, unwinding, or a low-lit room.

## Pulse Reactor
A high-octane EDM track, energetic and bright at 0.92 energy with a club-ready 128 BPM. Built for the dance floor, cardio sessions, or any peak-energy stretch of a set.

## Smoke and Brass
A jazz cut with a mellow, laid-back mood, easy at 0.42 energy and a relaxed 96 BPM. Its smoky horn lines fit dim rooms, late dinners, and slow evenings.

## Late Set
A romantic jazz ballad, tender and unhurried at 0.48 energy over a 92 BPM sway. The intimate mood makes it a natural for candlelit dinners and quiet close-of-night listening.

## Delta Dust
A blues song steeped in sadness, low-energy at 0.38 and a slow 82 BPM. The aching guitar and downcast feel suit rainy days and moments that call for something melancholy.

## Whiskey Lament
A mellow blues tune, easygoing at 0.44 energy over an 88 BPM shuffle. Warm and worn-in, it fits a quiet bar, a slow evening, or a reflective mood.

## Signal Bloom
An electronic track with a dreamy mood, floating at a mid 0.55 energy and 110 BPM. Its shimmering textures work for focus, gentle background listening, or a mellow evening.

## Rooftop Session
A hip-hop cut with a chill mood, relaxed at 0.55 energy over a laid-back 88 BPM. The easy groove suits hanging out, casual playlists, and low-stakes afternoons.

## Dust and Diesel
A country song carrying a sad mood, moderate at 0.45 energy and a steady 90 BPM. Its lonesome storytelling fits long drives and end-of-day reflection.

## Nocturne in Grey
A solo-piano classical piece, calm and spare at just 0.22 energy over a slow 58 BPM. The delicate, quiet mood makes it ideal for reading, focus, or drifting off to sleep.

## Slow Confession
An R&B ballad in a romantic mood, smooth at 0.48 energy over a 90 BPM groove. Its velvety vocals and warm feel suit intimate evenings and slow-dance moments.

## Ironclad Wrath
An aggressive metal track running near the ceiling at 0.97 energy and a blistering 152 BPM. The pounding drums and heavy guitars are built for intense workouts and high-adrenaline moments.

## Furnace Heart
A metal song with an intense mood, ferocious at 0.95 energy and a fast 146 BPM. Its wall-of-sound attack fits peak-effort training and anything that needs raw power.

## Harbor Sway
A reggae tune with a chill mood, relaxed at 0.52 energy over a loose 78 BPM. The offbeat groove is made for beach days, easy afternoons, and unwinding in the sun.

## Paper Lanterns
A gentle folk song in a calm mood, soft at 0.34 energy and a slow 84 BPM. Its acoustic warmth and quiet delivery suit cozy nights and unhurried listening.

## Velvet Sermon
A soul track with a romantic mood, warm at 0.58 energy over a 98 BPM groove. The rich vocals and heartfelt feel fit slow evenings and close-quarters moments.

## Halcyon Drift
A dreampop piece leaning fully dreamy, soft at 0.42 energy over a floating 102 BPM. Its hazy, reverb-washed guitars suit daydreaming, unwinding, and late-night reflection.

## Underwater Bloom
A dreampop track with a chill mood, gentle at 0.40 energy and a 100 BPM drift. The submerged, shimmering textures work well for relaxing and quiet background listening.

## Mirrorball Fever
A disco anthem in a happy mood, bright and danceable at 0.85 energy over a classic 120 BPM. Four-on-the-floor drums and a glittering groove make it a party and dance-floor staple.

## Saturday Voltage
An energetic disco cut at 0.82 energy and a steady 124 BPM. Its funky bassline and upbeat drive fit dance nights, getting-ready sets, and feel-good playlists.

## Velvet Hustle
A disco groove with a happy mood, upbeat at 0.80 energy over an 118 BPM strut. Smooth and retro, it suits dance floors and easy, celebratory moments.
