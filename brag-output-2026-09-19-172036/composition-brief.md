# Hyperframes Composition Brief: VPN Хелпдеск — преимущества для VPN-проектов

## Objective
25-секундная витрина шести возможностей панели для владельца VPN-сервиса: статистика,
данные о клиенте, изменение аккаунта клиента, ИИ-ответы, база знаний, шаблоны.
Видео идёт по настоящим экранам панели. Резервный канал доставки в сюжет НЕ входит.

## Output
- Composition directory: `<output-dir>/composition/`
- Rendered video: `<output-dir>/brag.mp4`
- Format: landscape — 1920x1080, 30 fps
- Duration: 25.0s

## Source Material
- Project root: `/home/user/vpn_bot_support`
- Primary files read: `app/static/statistics.jsx`, `app/static/dialogs.jsx`,
  `app/static/settings.jsx`, `app/static/index.html`, `app/customer.py`, `app/customers.py`,
  `README.md`, `HIDDEN_FEATURES.md`
- Product name: **VPN Хелпдеск**
- Strongest claim for the audience: оператор меняет аккаунт клиента из той же панели,
  где идёт переписка — вторая панель не нужна
- Copy that must appear verbatim (all from the project):
  - «Статистика», «данные за выбранный период», «Сегодня / 7 дней / 14 дней / 30 дней»
  - «Обращений сегодня», «Первый ответ (команда)», «Закрыто диалогов», «Ср. ответ (команда)»
    (`statistics.jsx:340–343`)
  - «Обращения по дням», «последние 14 дней», «сегодня», «обращ.» (`statistics.jsx` LineChart)
  - «Обращения по часам», «средние значения за 14 дней · пик в 21:00» (HeatmapChart)
  - «ИИ» — бейдж на ответе ИИ (`dialogs.jsx:258`)
  - «База знаний», «чанков · используется ИИ для поиска», «Загрузить документ»
    (`settings.jsx` KBSection)
  - «Поиск шаблонов...» (`dialogs.jsx:434`), «Шаблоны сообщений» (`settings.jsx`)
  - «Профиль», «Ключи», «Рефералы», «Обращения», «Действия» (`dialogs.jsx` UserInfoPanel tabs)
  - «Продлить подписку», «Докупить трафик», «Сменить локацию», «Сбросить все устройства»,
    поле «Месяцев» (`app/customer.py` ACTIONS)
  - «Pro · 500 ГБ» (`app/customers.py` plans), «VPN Хелпдеск» (экран входа)

## Creative Direction
- Tone preset: `app-store`
- Creative direction: чистая витрина продукта для владельца VPN-сервиса
- Interpretation: шесть чистых сцен, по одной строке пользы на сцену, слайд-входы содержимого,
  склейки точно по биту, ровный лёгкий слой SFX, никакой агрессии
- Angle: не «ещё один хелпдеск», а шесть конкретных вещей в одном окне; кульминация —
  действие над аккаунтом клиента прямо из карточки
- Hook: экран статистики, «Обращений сегодня» считает 0 → 128
- Outro / punchline: плитка «Х» → «VPN Хелпдеск» → «Одна панель для поддержки VPN»
- Avoid:
  - Generic SaaS language, выдуманные метрики достижений («в 10 раз быстрее»)
  - Abstract filler visuals
  - Сюжет про резервную отправку сообщений — он был в прошлом ролике и сюда не идёт
  - Любой редизайн: палитра и типографика строго из проекта

## Visual Identity
- Background `#0d0d12`; surfaces `#13131a` / `#1a1a24`; borders `#2a2a3a`
- Text `#f1f1f5`; muted `#868d99` (поднят из `#6b7280` ради WCAG AA — см. Deviations)
- Accent `#4F8EF7`, light `#7BA8F9`; логотип-градиент `#4F8EF7 → #A855F7`
- Success `#22c55e`, warn `#eab308`, danger `#ef4444`
- Display/body: Inter (локальные `assets/fonts/Inter-var-*.woff2`, `@font-face` в файле)
- Mono: JetBrains Mono (ID, даты, числа, метрики)

## Storyboard
Creative contract: `<output-dir>/brag-plan.md`.

Scene summary (границы посажены на бит-сетку 114.84 BPM):
1. **«Статистика»** — 0.00→5.28 — 4 карточки метрик по одной, счётчик 0→128,
   отрисовка графика «Обращения по дням», подъём тепловой карты. Строка:
   «Вся поддержка VPN — в одной панели».
2. **«ИИ отвечает»** — 5.28→8.44 — пузырь ИИ с бейджем «ИИ» отвечает клиенту сам. Строка:
   «ИИ отвечает сам — по вашей базе знаний».
3. **«База знаний»** — 8.44→10.54 — «24 чанка · используется ИИ для поиска», карточки чанков,
   подсветка того, из которого пришёл ответ, чипы ключевых фраз.
4. **«Шаблоны»** — 10.54→13.70 — «/» открывает «Поиск шаблонов...», выбор, отправка. Строка:
   «Остальное — готовым шаблоном».
5. **«Клиент и действия»** — 13.70→21.07 — карточка клиента с вкладками и профилем;
   затем ряд действий, клик «Продлить подписку», форма «Месяцев 3», «Применить», смена
   «Активен до» с зелёной вспышкой и тост. Строки: «Клиент виден целиком» →
   «И меняется прямо отсюда».
6. **«Логотип»** — 21.07→25.00 — плитка «Х», «VPN Хелпдеск», «Одна панель для поддержки VPN».

## Audio
- Audio role: тёплый деловой бед + ровный лёгкий слой акцентов (app-store)
- Audio arc: 0.28 на открытии → 0.30 рабочая → 0.33 на сцене действий → fade-out 23.4→25.0
- Music: `assets/music/happy-beats-business-moves-vol-11-by-ende-dot-app.mp3`
- Music treatment: fade-in 0.5s и весь профиль громкости — через `data-automation` volume lane
- Music cue guidance: preset скопирован в
  `assets/music/cues/happy-beats-business-moves-vol-11-by-ende-dot-app.music-cues.json`
  (114.84 BPM). **3 strong-cue лока:** 3.70 (отрисовка графика), 8.96 (подсветка чанка),
  17.91 (прилёт ряда действий). Остальное — beat-grid, список в `brag-plan.md`.
- Audio-reactive treatment: subtle; `assets/audio-data.js` (`rms` / `bass` / `treble`, 30 fps).
  Дышат: фон-свечение активного экрана (rms), присутствие подсвеченного чанка (bass),
  ореол плитки логотипа (treble). Никаких волновых форм, эквалайзеров, строба; текст не трогать.
- Audio-coupled moments:
  - Scene 1 — 4 карточки метрик (`interface/drop_002`), отрисовка графика (`impactSoft_medium_001`)
  - Scene 2 — прилёт пузыря ИИ (`interface/drop_001`)
  - Scene 3 — подсветка чанка (`interface/bong_001`)
  - Scene 4 — выбор шаблона (`interface/select_008`), отправка (`ui/click2`)
  - Scene 5 — клик «Продлить подписку» (`ui/click2`), применение действия (`impactSoft_medium_001`)
  - Scene 6 — посадка плитки логотипа (`impact/impactBell_heavy_000`)
- SFX selection guidance: только низкий/средний HF-risk по `sfx-analysis.md`; каждый звук
  привязан к видимому движению; `error_*` и `glitch_*` не используются — тон `app-store`
- SFX analysis guidance: `/tmp/brag-skill/skills/brag/assets/sfx/sfx-analysis.md`
- Audio files: скопированы в `<output-dir>/composition/assets/`

## Hyperframes Instructions
Domain skills: `hyperframes-core`, `hyperframes-animation`, `hyperframes-creative`,
`hyperframes-keyframes`, `hyperframes-cli`. /brag — собственный воркфлоу: intent-интервью и
generic product-launch маршрут не запускаются.

Structure: **модульная** — каждый экран отдельной сабкомпозицией под `compositions/`,
хост держит только полосу подписей, слоты и аудио. В прошлом ролике монолит был оправдан
непрерывной камерой по одному DOM-у; здесь шесть независимых экранов, и модульная структура —
родная для Hyperframes (снимает `nested_structure_needs_subcomposition` и `file_too_large`).

Requirements:
- Показывать настоящий UI проекта и настоящую копию (список выше).
- Каждая строка читается: короткая метка ≥ 0.8s, предложение ≥ 0.3s/слово в осевшем состоянии.
- Длительность 25.0s.
- Музыка + ~12 мотивированных SFX; аудио-реактивность subtle.
- Ровно 3 `// beat-locked` лока; последовательные прилёты — `// beat-grid`.
- Локальные шрифты с `@font-face`; локальный GSAP (CDN недоступен за прокси).
- Никаких сетевых запросов за обязательными ассетами, `Math.random()`, `Date.now()`,
  `repeat: -1`; не тве́нить `visibility`/`autoAlpha` на `.clip`.
- `npx hyperframes check` — единственный гейт перед рендером.

## Deviations / notes recorded up front
- **`--muted` `#6b7280` → `#868d99`** и тёмная подпись на кнопках фирменного синего:
  настоящие значения приложения валят WCAG AA, а контраст — часть гейта `hyperframes check`.
- **Графики статистики** (`LineChart`, `HeatmapChart`) и переключатель периода сейчас скрыты
  из `StatisticsScreen` (`HIDDEN_FEATURES.md` §3), но живут в `app/static/statistics.jsx` и
  возвращаются одной правкой. Показаны в ролике — без них «статистика» не читается как
  преимущество. Отмечено в `brag-plan.md`.
- **GSAP вендорен локально** (`assets/gsap.min.js`): cdn.jsdelivr.net недоступен через прокси.
