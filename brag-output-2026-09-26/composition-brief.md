# Hyperframes Composition Brief: VPN Хелпдеск

## Objective
Create a short launch-style brag video for VPN Хелпдеск that deliberately shows
BOTH sides of the product: the client's plain Telegram chat and the operator's
dark web admin panel — contrasted as two worlds of one product.

## Output
- Composition directory: `brag-output-2026-09-26/composition/`
- Rendered video: `brag-output-2026-09-26/brag.mp4`
- Format: landscape — 1920x1080
- Duration: ~22-24 seconds (15-25s window)

## Source Material
- Project root: `/home/user/vpn_bot_support`
- Primary files read: `app/static/index.html`, `app/static/dialogs.jsx`,
  `app/static/components.jsx` (styles, ticket list markup, AI-badge chat
  bubble, delivery-status ✓/✗/reserve states), `brag-plan.md`
- Product name: VPN Хелпдеск
- Tagline / strongest claim: «Клиент видит Telegram. Мы видим всё.»
- Key UI or visual moment to recreate: the operator panel's ticket row with
  pulsing status dot, the blue-bordered "ИИ" badge chat bubble, the
  "Взять в работу" claim action + template picker, and the delivery-status
  sequence — grey single check → red `✗ 400 BUSINESS_PEER_USAGE_MISSING` →
  yellow `✓✓ доставлено резервным каналом` — synced against the client's
  ordinary Telegram phone screen, which only ever shows a calm blue `✓✓`.
- Copy that must appear verbatim:
  - «По Wi-Fi работает, а на мобильном нет» (client, phone)
  - «Уже пробовал. Не помогло.» (client, phone)
  - «400 BUSINESS_PEER_USAGE_MISSING» (panel error code)
  - «доставлено резервным каналом» (panel fallback label)
  - «Клиент видит Telegram. Мы видим всё.» (outro line)

## Creative Direction
- Tone preset: `polished`
- Creative direction: сплит двух интерфейсов одного продукта — тёплый простой
  Telegram у клиента и тёмная профессиональная панель у оператора
- Interpretation: long holds, one short precise motion (0.3–0.5s) per beat;
  the world-to-world transition is the single largest visual gesture in the
  video — everything else stays restrained
- Angle: клиент видит только свой обычный чат в Telegram; вся инженерия
  (ИИ по базе знаний, живой вебсокет, резервный канал доставки) происходит на
  другой стороне экрана, которую клиент никогда не видит
- Hook: full-frame light Telegram phone screen, client typing «По Wi-Fi
  работает, а на мобильном нет» — looks like an ordinary support bot, nothing
  more
- Outro / punchline: «Клиент видит Telegram. Мы видим всё.»
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign of either real UI

## Visual Identity
- Background (panel side): `#0d0d12`
- Surface / cards (panel side): `#13131a`, `#1a1a24`; borders `#2a2a3a`
- Text (panel side): `#f1f1f5`; muted `#868d99` (raised from the app's
  `#6b7280` for WCAG AA on dark backgrounds)
- Accent: `#4F8EF7`; logo gradient `#4F8EF7 → #A855F7`
- Status colors: `#eab308` (reserve delivery), `#ef4444` (error)
- Background (client side): Telegram light — white / `#f7f8fa` chrome,
  outgoing bubble `#e7f3ff`, incoming bubble `#ffffff` with `#e5e8ea` border
- Display font: Inter 600/700 (local variable woff2, cyrillic+latin)
- Body font: Inter 400/500; monospace accents: JetBrains Mono
- Visual references from the project: ticket `ConvCard` pulsing red dot,
  `MessageBubble` AI badge + delivery-status ticks, operator login/brand tile
  gradient `#4F8EF7 → #A855F7`

## Storyboard
Use the storyboard in `brag-plan.md` as the creative contract. Exact
composition timings below adjust the plan's approximate seconds to land 3 of
the transitions on real detected beats (`assets/music/cues/*.music-cues.json`,
strong cues at 3.18s, 16.86s) while keeping everything else on natural,
readability-first timing.

Scene summary (global seconds):
1. Клиент — 0.00–3.18s — full-frame light Telegram phone, client types the
   first message, nothing hints at a second interface yet.
2. Граница — 3.18–5.28s — phone shrinks into a bottom-left corner window,
   dark panel wipes in from the right, a thin vertical divider marks the
   boundary; caption «Клиент видит Telegram».
3. Тикет и ИИ — 5.28–9.50s — ticket lands in the panel list with a pulsing
   dot, the "ИИ" badge bubble answers from the knowledge base while the
   client's second message mirrors into both the phone (small corner window)
   and the panel chat; caption «ИИ отвечает по базе знаний».
4. Оператор — 9.50–14.22s — cursor claims the ticket ("Взять в работу"),
   opens the template panel, sends a reply; caption «Оператор дожимает
   шаблоном».
5. Сбой и резервный канал — 14.22–19.49s — delivery flips to red
   `✗ 400 BUSINESS_PEER_USAGE_MISSING`, holds, then flips to yellow
   `✓✓ доставлено резервным каналом` (beat-locked at 16.86s) exactly as the
   phone's bot bubble quietly lands with an ordinary blue `✓✓`; caption
   «Резервный канал — клиент ничего не заметил».
6. Оба мира — 19.49–23.70s — panel and phone resize side by side, hold, then
   dissolve into the logo card: gradient tile "Х", "VPN Хелпдеск", and the
   punchline «Клиент видит Telegram. Мы видим всё.».

## Audio
- Audio role: sparse professional accents over one steady, clean music bed
- Audio arc: warm/quiet under the Telegram side, marginally denser under the
  panel side — a tonal cue for the world switch, not a dramatic swell
- Music: `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3` (114.84 BPM)
- Music treatment: fade in under scene 1 to ~0.28, settle ~0.30–0.32 across
  the panel scenes, fade out under the outro logo
- Music cue guidance: rich preset at
  `assets/music/cues/happy-beats-business-moves-vol-11-by-ende-dot-app.music-cues.json`
  (`strongCues` + `beats`). Used as bias, not control — most scene cuts land
  on convenient natural timings that also happen to sit on strong cues
  (3.18s, 5.28s, 9.50s, 14.22s, 19.49s all measured strong beats); only the
  world-transition start (3.18s) and the reserve-delivery reveal (16.86s) are
  explicitly beat-locked, per the 1–3-lock guidance.
- Audio-reactive treatment: subtle — the panel's own ambient background glow
  breathes a few percent with music RMS once the panel is on screen. No
  waveform/equalizer visuals.
- Audio-coupled moments:
  - phone typing dots (scenes 1, 3, 5) — soft keypress ticks, randomized files
  - border wipe (scene 2 start, 3.18s) — soft drop as the panel reveals
  - "Взять в работу" click (scene 4) — click SFX on cursor action
  - delivery failure (scene 5, ~14.5s) — dry negative accent, no drama
  - reserve delivery + phone reply landing (scene 5, 16.86s, beat-locked) —
    soft bell, synced across both screens
  - logo landing (scene 6) — heavier bell, rings slightly over the music
    fade-out
- SFX selection guidance: match visible motion only — a click SFX needs a
  visible cursor/button action, a bell needs a visible landing. Keep it
  sparse per the `polished` tone: roughly 8 total cues across 23.7s, softly
  mixed (0.45–0.7), nothing aggressive.
- SFX analysis guidance: not read in this run (no `sfx-analysis.md` bundled
  with the fetched assets); chosen sounds are the same restrained families
  (`interface/drop_*`, `interface/bong_001`, `interface/select_008`,
  `interface/error_005`, `impact/impactSoft_medium_001`,
  `impact/impactBell_heavy_000`, `keyboard/keypress-*`) already used
  successfully in the prior run of this same product.
- Exact SFX choice: filenames/timestamps finalized in `index.html` /
  `compositions/panel.html` once animation timing was implemented.
- Audio files: copied into `composition/assets/` (music, cues JSON, and the
  sfx/keyboard files listed above) before composing.

## Hyperframes Instructions
Composition built directly against the current `hyperframes-core` /
`hyperframes-animation` / `hyperframes-creative` / `hyperframes-keyframes` /
`hyperframes-cli` skills (installed locally via `npx hyperframes skills
update`). `/brag` is its own workflow — the generic `hyperframes` intent
interview and its promo/launch-video routing were not used.

Implementation notes handed to the build (decided during composition, not by
`/brag`):
- Monolithic-ish hybrid: `index.html` hosts a persistent phone element
  (host-root, animated on the MAIN timeline across all 6 scenes: full-frame →
  corner window → left-half "both worlds" pose) plus a persistent panel
  sub-composition (`compositions/panel.html`) mounted from 3.18s, animated the
  same way for its scene-6 resize. The panel sub-comp itself uses the
  "multi-scene merge" archetype internally (phases, not multiple slots) for
  the ticket/AI/operator/failure/reserve progression, since it is one
  continuously-growing chat thread and ticket state.
- Real UI fidelity: panel colors/classes are pulled directly from
  `app/static/dialogs.jsx` (`DeliveryStatus`, `MessageBubble` ai/operator
  variants, `ConvCard` pulsing dot) and `app/static/index.html` (brand tile
  gradient, login screen palette).
- `npx hyperframes check` run as the pre-render gate; contrast findings (if
  any) fixed by nudging the flagged color within the same palette family per
  the tool's suggested value.
