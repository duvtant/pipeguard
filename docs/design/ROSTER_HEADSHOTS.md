# Roster headshots: prompts for the image generator

Twelve technicians on the Roster currently show a letter in a coloured circle. These prompts make a realistic photo for each. The app already supports them: drop the finished images in `docs/assets/headshots-src/` named `tech-1.png` ... `tech-12.png`, run `./scripts/make-headshots`, and the Roster picks them up. Anyone without a photo keeps the letter.

**These are fictional people.** Do not use a real person's name, face or a "looks like (celebrity)" prompt. In the README, say the roster photos are AI-generated (the handbook has an AI-and-ethics section, and honesty is cheap here).

---

## 1. What the research says (and what I took from it)

Sources: OpenAI's gpt-image prompting guide [read directly], and several 2026 prompt guides [search summaries, so treat as leads].

| Technique | Why | Source |
|---|---|---|
| **Describe it as a real photo taken in the moment**, not as a "beautiful portrait" | Words that imply studio polish or staging push the result toward a staged, glossy look | OpenAI cookbook (gpt-image-1.5 guide): https://developers.openai.com/cookbook/examples/multimodal/image-gen-1.5-prompting_guide |
| **Name a real lens and aperture** (85 mm f/1.8, 50 mm f/2) instead of "8K, ultra detailed, masterpiece" | Camera and composition terms steer realism more reliably than generic quality words, and wide lenses (under 35 mm) distort faces and look uncanny | OpenAI guide; https://gptprompts.ai/realistic-ai-image-prompts ; https://www.makeaiphotos.com/blog/how-to-make-ai-photos-look-realistic/ |
| **Ask for real skin texture explicitly**: pores, fine lines, uneven tone, under-eye shadows. "No glamorisation, no heavy retouching" | Over-smooth skin is the number-one tell | OpenAI guide; https://fiddl.art/blog/en/ai-portrait-prompts |
| **One small imperfection per person**: a flyaway hair, slight asymmetry, a chipped tooth, a scar, a crease from a hard hat | Perfect symmetry reads as synthetic | gptprompts.ai, imagera.ai |
| **Specific, real light**: overcast daylight, low winter sun, fluorescent plus window light, floodlight at night | "Soft studio lighting" is the default AI look; real places have messy light | OpenAI guide (lighting cues); Nano Banana guides (colour temperature) |
| **Prompt order: setting, then subject, then details, then constraints**, and **state exclusions plainly** ("no watermark, no logos, no text") | The official structure; negatives work best as plain statements | OpenAI guide |
| **Say what it is for** ("a small avatar in a work app") | Sets the level of polish | OpenAI guide |
| **Vary on purpose.** No guide covers batch variety, so we build it into the table below: different age, setting, light, framing and expression for each person | Without this, a batch comes back with one face and one background | (our own rule) |

**Avoid:** "flawless", "8K", "masterpiece", "ultra-detailed", "perfect skin", "beauty", "cinematic grade", "HDR", and any lens under 35 mm for a face.

---

## 2. Settings for every image

- **Size and shape:** square, **1024 x 1024**. Keep the face about 55 to 65 percent of the frame height, eyes about 40 percent down from the top, so a circle crop never cuts the head.
- **Format:** PNG or JPG out of the generator. `make-headshots` writes 512 x 512 JPEGs (about 30 to 60 KB each), shown at 36 px in the Roster and up to 72 px elsewhere.
- **One image at a time**, each in its own request (with its own random seed). Do not ask for "a team photo" or "12 headshots".
- **Download at full size**, then check each at 100 percent before keeping it.

## 3. The prompt template

```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app.
SETTING: {where, and what is behind the person, out of focus}.
SUBJECT: {age}-year-old {description, in plain words}. {Hair, facial hair, glasses}. {Clothing, with real wear: scuffs, creases, a faded logo-free patch}. {Expression and where they are looking}.
CAMERA: shot on a full-frame camera, {85mm f/1.8 | 50mm f/2}, head-and-shoulders, eye level, subject centred with room above the head, shallow depth of field.
LIGHT: {specific real light}.
REAL SKIN AND DETAIL: visible pores, fine lines, uneven skin tone, small natural asymmetry, {one imperfection}. Honest and unposed. No glamorisation, no heavy retouching.
CONSTRAINTS: square 1:1. No text, no logos, no watermark, no helmets with printed words, no extra fingers or hands near the face, no studio backdrop, no beauty filter, no airbrushed skin, no HDR, no illustration or painting style.
```

**If your generator has a separate "negative prompt" box** (Stable Diffusion, Midjourney `--no`), paste this there as well:
`plastic skin, airbrushed, flawless, beauty filter, glamour, studio backdrop, HDR, oversharpened, 3d render, illustration, cartoon, uncanny teeth, extra fingers, hands covering face, text, logo, watermark, identical background, stock photo look`

---

## 4. The twelve people

Roster order matches the app (id, station, shift). Ages 26 to 60, deliberately mixed in gender, background, framing, expression and light. The backgrounds are all different. Nothing here depends on a name; these are invented people.

**Variety at a glance**

| id | Name | Station | Shift | Setting | Light | Framing | Mood |
|---|---|---|---|---|---|---|---|
| 1 | Aiden Walker | Edson | day | compressor yard | overcast daylight | head and shoulders | relaxed half smile |
| 2 | Priya Nair | Edson | night, backup | control room | monitor glow plus desk lamp | tighter, slight angle | calm, focused |
| 3 | Marc Tremblay | Grande Prairie | day | snowy site | low winter sun | tight, off-centre eyes | warm laugh |
| 4 | Chloe Ouellet | Grande Prairie | night, backup | parts workshop | fluorescent plus window | looking slightly away | tired, friendly |
| 5 | Dmitri Volkov | Hinton | day | truck bay | overhead shop light | straight on | serious |
| 6 | Sana Rahman | Hinton | night | yard at dusk | floodlight rim light | three-quarter angle | quietly confident |
| 7 | Tom Reilly | Whitecourt | day | pickup truck cab | window light | head and shoulders, chin down | wry grin |
| 8 | Ngozi Okafor | Whitecourt | night | plant corridor | warm sodium light | straight on | composed half smile |
| 9 | Lena Fischer | Drumheller | day | badlands edge | hard noon sun, open shade | looking off to the side | squinting, mid-laugh |
| 10 | Mateo Silva | Drumheller | night | control room doorway | cool indoor with warm spill | three-quarter | tired smile |
| 11 | Hannah Cho | Edson | day | corrugated steel wall | soft shade | straight on | direct, neutral |
| 12 | Jon Blackfoot | Hinton | day, backup | foothills at golden hour | low warm sun | head and shoulders | calm, thoughtful |

### The prompts (copy each into its own request)

**1. Aiden Walker** (Edson, day)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: the yard of a gas compressor station on a flat overcast morning, pipework and a pale grey metal building softly out of focus behind. SUBJECT: 33-year-old man, light brown short hair, a day of stubble, slightly sunburnt nose. Orange hi-vis vest over a grey fleece, vest scuffed and creased. Relaxed half smile, looking at the camera. CAMERA: full-frame camera, 85mm f/1.8, head-and-shoulders, eye level, centred with room above the head, shallow depth of field. LIGHT: soft overcast daylight, no harsh shadows. REAL SKIN AND DETAIL: visible pores, fine lines at the eyes, uneven skin tone, slight asymmetry in the smile, one flyaway hair. Honest and unposed, no glamorisation, no heavy retouching. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no studio backdrop, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**2. Priya Nair** (Edson, night, backup)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: a quiet industrial control room at night, rows of monitors glowing blurred behind her. SUBJECT: 38-year-old South Asian woman, dark hair in a low loose bun with a few strands escaped, thin-framed glasses, small gold stud earrings. Navy flame-resistant work shirt with the collar slightly turned. Calm, focused expression, eyes on the camera, a slight tilt of the head. CAMERA: full-frame camera, 85mm f/1.8, tight head-and-shoulders, slightly angled, shallow depth of field. LIGHT: cool monitor glow from one side and a warm desk lamp from the other. REAL SKIN AND DETAIL: visible pores, faint dark circles under the eyes, a little shine on the forehead, reflections in the glasses, natural asymmetry. Honest, unposed. CONSTRAINTS: square 1:1. No text on screens, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**3. Marc Tremblay** (Grande Prairie, day, French speaker)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: an outdoor compressor site in deep winter, snow on the ground and on distant pipework, pale sky, all softly out of focus. SUBJECT: 52-year-old white man, grey-flecked beard, deep laugh lines, wearing a dark wool toque and a heavy brown insulated work jacket with snow dusted on the shoulders and frost in his beard. A genuine warm laugh, looking just off the camera. CAMERA: full-frame camera, 85mm f/2, tight head-and-shoulders, eyes slightly off-centre, shallow depth of field. LIGHT: low winter sun from the side, warm on his cheek, cold blue shadows. REAL SKIN AND DETAIL: windburned cheeks, visible pores, deep lines, uneven colour on the nose, a few grey hairs poking out of the toque. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**4. Chloe Ouellet** (Grande Prairie, night, backup, French speaker)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: a parts workshop with shelving, bins and a workbench blurred behind her, a window letting in grey light. SUBJECT: 28-year-old woman, fair skin with freckles across the nose and cheeks, auburn hair in a thick side braid, a thin scar through the left eyebrow. Grey work t-shirt under an open canvas jacket with a smear of grease on the cuff. Friendly, slightly tired expression, gaze drifting just past the camera. CAMERA: full-frame camera, 50mm f/2, head-and-shoulders, eye level, shallow depth of field. LIGHT: flat fluorescent overhead mixed with cool daylight from the window. REAL SKIN AND DETAIL: freckles, visible pores, slight redness on the nose, faint shadows under the eyes, flyaway hairs from the braid. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**5. Dmitri Volkov** (Hinton, day)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: the open door of a service truck bay, tools hanging on a pegboard blurred behind him. SUBJECT: 45-year-old man of Eastern European descent, shaved head with a little stubble, strong dark eyebrows, a broken-and-healed nose. Dark grey hooded sweatshirt under a worn yellow-green hi-vis jacket. A serious, direct look at the camera, mouth relaxed. CAMERA: full-frame camera, 85mm f/2, head-and-shoulders, eye level, centred, shallow depth of field. LIGHT: harsh overhead shop lighting giving strong shadows under the brow. REAL SKIN AND DETAIL: pores, razor stubble, forehead creases, a patch of dry skin, a small nick on the chin. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**6. Sana Rahman** (Hinton, night)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: the yard of a compressor station at dusk, floodlights just coming on, pipework and a chain-link fence blurred behind her. SUBJECT: 34-year-old woman of Bangladeshi descent wearing a plain dark teal hijab and a charcoal fleece vest over a work shirt, safety glasses pushed up on top of the scarf. Quietly confident, a hint of a smile, face turned three-quarters to the camera, eyes on the lens. CAMERA: full-frame camera, 85mm f/1.8, head-and-shoulders, three-quarter angle, shallow depth of field. LIGHT: warm floodlight from behind-left giving a soft rim light, cool blue dusk fill on her face. REAL SKIN AND DETAIL: visible pores, small mole near the jaw, slightly uneven skin tone, a little shine on the cheekbone, natural asymmetry. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**7. Tom Reilly** (Whitecourt, day)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: inside the cab of a pickup truck, a window and a blurred forest-service road behind him. SUBJECT: 60-year-old white man with a weathered face, grey moustache, bushy eyebrows, a faded plain navy ball cap with no print, denim work shirt buttoned to the collar. A wry grin, chin slightly lowered, looking at the camera. CAMERA: full-frame camera, 50mm f/2, head-and-shoulders, eye level, shallow depth of field. LIGHT: soft daylight from the side window across half his face. REAL SKIN AND DETAIL: deep wrinkles, sun spots, broken capillaries on the cheeks, visible pores, grey stubble, natural asymmetry. Honest and unposed, no glamorisation. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**8. Ngozi Okafor** (Whitecourt, night)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: a long industrial plant corridor at night, pipes and railings fading into the distance, warm lights blurred behind her. SUBJECT: 40-year-old Black woman with short natural hair, small hoop earrings, clear safety glasses resting on her nose, reflective vest over a dark work jacket. A composed half smile, looking at the camera. CAMERA: full-frame camera, 85mm f/1.8, head-and-shoulders, eye level, centred, shallow depth of field. LIGHT: warm sodium-style overhead lights from above, a soft highlight on the cheekbones. REAL SKIN AND DETAIL: visible pores, a few fine lines, small areas of uneven pigmentation, natural sheen, small reflections in the glasses. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**9. Lena Fischer** (Drumheller, day)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: the edge of the Alberta badlands, dry layered hills and a flat dirt track softly out of focus behind her. SUBJECT: 26-year-old white woman with a tanned face, a blonde ponytail with loose strands, sunglasses pushed up into her hair, sleeves of a sun-faded work shirt rolled to the elbow. Caught mid-laugh, squinting slightly, looking off to the side. CAMERA: full-frame camera, 85mm f/2, head-and-shoulders, off-centre, shallow depth of field. LIGHT: hard midday sun with her face in open shade, bright background. REAL SKIN AND DETAIL: freckles, sun-dried lips, visible pores, a little peeling on the nose, squint lines, natural asymmetry in the laugh. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**10. Mateo Silva** (Drumheller, night)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: the doorway of a small control building at night, a lit interior blurred behind him. SUBJECT: 29-year-old Latino man with dark curly hair, a short beard with a patchy cheek, an unzipped flame-resistant coverall over a plain t-shirt. A tired but genuine smile, face turned three-quarters, looking at the camera. CAMERA: full-frame camera, 50mm f/2, head-and-shoulders, three-quarter angle, shallow depth of field. LIGHT: cool light from the doorway behind and a warm spill of light on his face. REAL SKIN AND DETAIL: visible pores, five-o'clock shadow, small acne scar on the cheek, bags under the eyes, a crease from the coverall collar. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**11. Hannah Cho** (Edson, day)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: standing against the pale corrugated steel wall of a site building, the ridges of the metal softly out of focus. SUBJECT: 31-year-old woman of Korean descent with shoulder-length straight black hair tucked behind one ear, a quilted dark green vest over a grey crew-neck, a lanyard-free collar. A direct, neutral look at the camera, lips closed. CAMERA: full-frame camera, 85mm f/1.8, head-and-shoulders, eye level, centred, shallow depth of field. LIGHT: soft open shade, even but not flat, a little cool. REAL SKIN AND DETAIL: visible pores, a faint blemish near the chin, tiny fine lines, slight asymmetry, a few stray hairs across the forehead. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

**12. Jon Blackfoot** (Hinton, day, backup)
```
A candid photograph, not a studio shot, to be used as a small profile photo in a work app. SETTING: a roadside gravel pullout with the Rocky Mountain foothills and a few spruce trees softly out of focus behind him, late afternoon. SUBJECT: 38-year-old Indigenous man from the Blackfoot Confederacy, long dark hair tied back, a trimmed goatee, a tan canvas work jacket over a flannel shirt. Ordinary workwear only, no regalia, no headdress, no beadwork, no stereotypes. A calm, thoughtful expression, looking at the camera. CAMERA: full-frame camera, 85mm f/1.8, head-and-shoulders, eye level, shallow depth of field. LIGHT: low warm golden-hour sun from the side, soft shadows. REAL SKIN AND DETAIL: visible pores, fine lines at the eyes, uneven tone, wind-dried lips, a few loose strands of hair across the face. Honest and unposed. CONSTRAINTS: square 1:1. No text, no logos, no watermark, no beauty filter, no airbrushed skin, no HDR, no illustration style.
```

---

## 5. Check each image before you keep it

- **Eyes:** both the same size and pointing the same way, with believable highlights.
- **Teeth and ears:** no extra or merged teeth, ears the same shape on both sides.
- **Hair edges and glasses:** no melted edges, glasses frames continuous.
- **Hands:** none near the face (they are the classic failure).
- **Background:** real-looking, different from the others. If a background looks like generic smooth blur, re-roll.
- **Skin:** if it looks waxy, re-roll with the skin line made stronger ("visible pores, fine lines, uneven tone") and drop any "perfect" words.
- **A circle crop:** check the face still looks right at 36 px.
- **Resemblance:** if anyone looks like a real, recognisable person, re-roll.

Then: save as `docs/assets/headshots-src/tech-<id>.png`, run `./scripts/make-headshots`, open `/roster`.
