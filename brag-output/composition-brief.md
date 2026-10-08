# Hyperframes Composition Brief: VPN Хелпдеск (vpn_bot_support)

## Objective
Create a short launch-style brag video for **VPN Хелпдеск** — the operator helpdesk panel in
this repository. The video must play out entirely inside a recreation of the real panel UI and
end on the feature nobody demos: the fallback delivery channel.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 24.5s (выросла с 21.2s ради порога читаемости финальных строк)

## Source Material
- Project root: `/home/user/vpn_bot_support`
- Primary files read: `README.md`, `HIDDEN_FEATURES.md`, `app/static/index.html`,
  `app/static/dialogs.jsx`, `app/static/components.jsx`, `.env.example`
- Product name: **VPN Хелпдеск** (`Хелпдеск · VPN Support`)
- Tagline / strongest claim: «Тикеты из Telegram. Ответы из панели.» — плюс резервный канал
  доставки по MTProto, когда Telegram отвечает `400 BUSINESS_PEER_USAGE_MISSING`
- Key UI to recreate: трёхколоночная тёмная панель — список тикетов слева, переписка в центре,
  карточка клиента справа; ряд пилюль ВПН-сервисов под шапкой; пузырь ИИ в синей рамке с
  бейджем «ИИ»; панель автодополнения шаблонов по «/»; индикатор доставки ✓ / ✗ / ✓✓
- Copy that must appear verbatim (all from the project):
  - «По Wi-Fi работает, а на мобильном нет» (заголовок сценария базы знаний, `README.md` §02.2)
  - «Все сервисы», «GruVPN» (`.env.example`: `DEFAULT_SERVICE_NAME=GruVPN`)
  - «В работе», «Ожидание», «Очередь», «ИИ», «Закрытые» (разделы списка, `dialogs.jsx`)
  - «Взять в работу» (`dialogs.jsx:1063`)
  - «Поиск шаблонов...» (`dialogs.jsx:434`)
  - «ИИ» — бейдж на ответе ИИ (`dialogs.jsx:258`)
  - `400 BUSINESS_PEER_USAGE_MISSING` (`README.md`, раздел «Резервная отправка ответа»)
  - «доставлено резервным каналом» (`dialogs.jsx:298`)
  - «VPN Хелпдеск» (экран входа, `index.html`)

## Creative Direction
- Tone preset: `polished`
- Creative direction: тихий премиальный фильм про рабочий инструмент — «панель, которая уже
  подумала про плохой день»
- Interpretation: длинные удержания, одна читаемая строка за сцену, короткое точное движение
  (0.3–0.5s), мягкие кроссфейды и чистые склейки. Никаких зумов-ударов, вспышек и строба.
- Angle: не ролик про «оптимизацию поддержки», а 21 секунда жизни одного тикета — от фразы
  клиента в Telegram до ответа, который дошёл, хотя Telegram его не принял. Продукт показывает
  себя в работе, а не рассказывает о себе.
- Hook: чёрный кадр, печатается один входящий пузырь Telegram с настоящей фразой из базы знаний.
- Outro / punchline: отъезд на всю панель → градиентная плитка «Х» → «VPN Хелпдеск» →
  «Тикеты из Telegram. Ответы из панели.»
- Avoid:
  - Generic SaaS language (никаких «оптимизируйте поддержку», «10x быстрее»)
  - Abstract filler visuals (градиентные washes, частицы, абстрактная графика)
  - Unrelated visual redesign — палитра и типографика строго из проекта
  - Выдуманные метрики и цифры достижений

## Visual Identity
- Background: `#0d0d12`
- Surfaces: `#13131a` (панели, попапы), `#1a1a24` (пузыри, строки, чипы)
- Borders: `#2a2a3a`
- Text: `#f1f1f5`; muted `#6b7280`
- Accent: `#4F8EF7`; логотип-градиент `#4F8EF7 → #A855F7`
- Статусы: `#eab308` (ожидание / резервная доставка), `#ef4444` (вызван оператор / ошибка)
- Display font: Inter 600/700 (локальные `assets/fonts/Inter-var-*.woff2`, `@font-face` в файле)
- Body font: Inter 400/500; коды и время — JetBrains Mono 400/500 (локальные woff2)
- Visual references from the project: `rounded-2xl` пузыри с «хвостом» (`rounded-tl-md` /
  `rounded-tr-md`), синяя полоска-индикатор слева у активной строки, пульсирующая красная точка
  у тикета с вызовом оператора, пилюли сервисов со счётчиками, `scrollbar-thin` колонки

## Storyboard
Creative contract: `brag-output/brag-plan.md`.

Scene summary:
1. **«Сообщение»** — 0.0→4.2 — печатается пузырь «По Wi-Fi работает, а на мобильном нет»
   + «21:47 · Telegram»; 2.3s осевшего времени.
2. **«Тикет»** — 4.0→7.7 — панель проявляется; пилюли сервисов по beat-grid; строка тикета
   садится наверх списка с пульсирующей точкой. Строка: «Из Telegram — в панель».
3. **«ИИ → оператор»** — 7.7→12.2 — пузырь ИИ в синей рамке с бейджем «ИИ»; клиент пишет
   «Уже пробовал. Не помогло.»; курсор жмёт «Взять в работу» (9.29); статус → «В работе»;
   «/» открывает панель шаблонов «Поиск шаблонов...». Строка: «ИИ не справился — зовёт оператора».
4. **«Резервный канал»** — 12.2→18.5 — ответ уходит; ✓ → красный ✗
   `400 BUSINESS_PEER_USAGE_MISSING` (13.11); пауза 2.2s; «повтор резервным каналом» (15.29);
   жёлтые ✓✓ и «доставлено резервным каналом» (17.47). Строка: «Telegram отказал. Ответ дошёл.»
5. **«Панель целиком»** — 18.5→24.5 — отъезд на три колонки, ~0.9s чистого кадра, уход в
   чёрное, плитка «Х» (20.75), «VPN Хелпдеск» (21.28), «Тикеты из Telegram. Ответы из панели.» (21.84)

## Audio
- Audio role: ровный чистый бед + редкие мотивированные акценты (professional restraint)
- Audio arc: тихий вход (0.28) → рабочая ровность (0.30) → лёгкий подъём на выкупе (0.32) →
  fade-out под логотип, финальный колокол звенит в уходящей музыке
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady & clean)
- Music treatment: старт 0.0, fade-in 0.6s, fade-out 19.8→21.2 через `data-automation` volume lane
- Music cue guidance: preset скопирован в
  `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`
  (tempo 109.96 BPM). Strong-cue локи (3, максимум по политике):
  **9.29s** — клик «Взять в работу»; **13.11s** — красный ✗; **17.47s** — жёлтые ✓✓ (главный выкуп).
  Beat-grid: пилюли 4.39 / 4.91 / 5.34, тикет 6.00, ИИ 8.19, клиент 8.74,
  шаблоны 10.37 / 10.93 / 11.46 / 12.02, системная запись 15.29, финал 20.75 / 21.28 / 21.84.
- Audio-reactive treatment: subtle. Данные извлечены в `assets/audio-data.js`
  (`rms` / `bass` / `treble`, 30fps, 740 кадров, обрезано под длину ролика). По ним дышат:
  свечение синей полоски активной строки тикета (bass), лёгкое присутствие карточки переписки
  (rms), мягкое свечение плитки логотипа в финале (treble). Никаких волновых форм,
  эквалайзеров, строба и пульсации текста — амплитуда ≤ 6% на текстовых блоках.
- Audio-coupled moments:
  - Scene 1 — печать пузыря: тики клавиш (`keyboard/keypress-*`, каждый 3-й символ, 0.35)
  - Scene 2 — посадка строки тикета: `interface/drop_001` (0.5)
  - Scene 3 — клик «Взять в работу»: `ui/click2` (0.55, ровно в кадре нажатия;
    `interface/click_002` отброшен — 0.01s, физически не слышно);
    выбор шаблона: `interface/select_008` (0.45)
  - Scene 4 — провал доставки: `impact/impactSoft_medium_001` (0.5, сухой, не комедийный);
    выкуп ✓✓: `impact/impactBell_heavy_000` (0.55)
  - Scene 5 — посадка плитки логотипа: `interface/bong_001` (0.5)
- SFX selection guidance: только низкий/средний HF-risk по `sfx-analysis.md`; каждый звук
  привязан к видимому движению; `error_*` намеренно НЕ используется — комедийный тембр
  противоречит тону `polished`
- SFX analysis guidance: `/tmp/brag-skill/skills/brag/assets/sfx/sfx-analysis.md`
- Exact SFX choice: файлы уже скопированы в `assets/sfx/`; тайминги ставятся по фактической
  анимации, звук в начале движения, не в конце
- Audio files: скопированы в `brag-output/composition/assets/`

## Hyperframes Instructions
Domain skills loaded: `hyperframes-core`, `hyperframes-animation`, `hyperframes-creative`,
`hyperframes-keyframes`, `hyperframes-cli` (установлены через `npx hyperframes skills update`).
/brag — собственный воркфлоу: intent-интервью и generic product-launch маршрут не запускаются.

Requirements:
- Показать настоящий UI проекта: пузыри, список тикетов, бейдж «ИИ», индикатор доставки.
- Весь текст читается: короткая метка ≥ 0.8s, предложение ≥ 0.3s/слово в осевшем состоянии.
- Длительность 24.5s (в окне 15–25s).
- Музыка + 6 SFX-акцентов; аудио-реактивность subtle по `assets/audio-data.js`.
- 3 strong-cue лока (8.74 / 13.11 / 17.47), помеченные `// beat-locked`; последовательные
  прилёты — по beat-grid, помечены `// beat-grid`.
- Локальные шрифты с `@font-face` (lint: `font_family_without_font_face`).
- Никаких сетевых запросов за обязательными ассетами, `Math.random()`, `Date.now()`,
  `repeat: -1`; не тве́нить `visibility`/`autoAlpha` на `.clip`.
- `npx hyperframes check` — единственный гейт перед рендером.


## Deviations from the brief (decided during composition)
- **Длительность 21.2s → 24.5s.** Финальная строка и подпись выкупа не укладывались в порог
  читаемости. Пейсинг сцен не менялся, добавлено время удержания.
- **`--muted` поднят `#6b7280` → `#868d99`.** Настоящий серый приложения даёт 3.5–4.0:1 на
  `#1a1a24` и валит WCAG AA в `hyperframes check` (гейт /brag). Новый даёт ≥5:1 на всех
  поверхностях композиции. Все остальные цвета — ровно из проекта.
- **Белый текст на `#4F8EF7` → `#0d0d12`** на кнопке «Взять в работу» и бейдже «ИИ» (3.2:1).
  Фирменный синий сохранён точно, читаемость обеспечена тёмной подписью.
- **GSAP вендорен локально** (`assets/gsap.min.js`): cdn.jsdelivr.net недоступен через прокси,
  и сетевой запрос во время рендера в любом случае противоречит правилам детерминизма.
- **Композиция монолитная.** `hyperframes check` оставляет 7 предупреждений
  (`composition_file_too_large`, `nested_structure_needs_subcomposition`) — это рекомендации
  по эргономике Studio. Разбивать сцены на сабкомпозиции здесь нельзя без потери главного
  приёма: одна непрерывная камера ведёт по одному и тому же DOM-у панели, а таймлайн
  сабкомпозиции не дотягивается до элементов хоста. Ошибок — ноль.
