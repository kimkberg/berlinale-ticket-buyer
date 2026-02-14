<div align="center">

# 🎬 Berlinale Ticket Buyer

**Automated ticket sniper for the Berlin International Film Festival**

Never miss a Berlinale screening again.

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=flat-square&logo=playwright&logoColor=white)](https://playwright.dev)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

[English](#features) | [中文](#中文) | [Fran&ccedil;ais](#français) | [Deutsch](#deutsch) | [Espa&ntilde;ol](#español) | [Portugu&ecirc;s](#português) | [日本語](#日本語) | [한국어](#한국어)

</div>

---

## Why This Exists

Berlinale tickets go on sale **3 days before each screening at exactly 10:00 CET**. Popular films sell out in seconds. This tool:

1. **Monitors** the entire festival programme in real-time
2. **Schedules** ticket grabs to fire at the exact sale moment
3. **Automates** the Eventim checkout flow via browser automation
4. **Watches** sold-out screenings and auto-grabs when tickets return

No more alarm clocks. No more refreshing pages. Just pick your films and let it run.

---

## Features

- **Full Programme Browser** &mdash; Browse all 340+ films across 25 sections, search by title, filter by date
- **Real-time Ticket Status** &mdash; Live updates via WebSocket, see available / pending / sold-out at a glance
- **Precision Grab Scheduling** &mdash; Pre-heats the browser, opens the page 30s early, refreshes at the exact sale second
- **Sold-out Watching** &mdash; Polls every 5-15s, auto-triggers grab when tickets reappear (accredited returns, quota reallocation)
- **Persistent Browser Session** &mdash; Log into Eventim once, stays logged in across restarts
- **Sale Countdown Timers** &mdash; Live countdown to each screening's ticket sale time
- **Dark Theme UI** &mdash; Clean, responsive single-page app

<div align="center">

```
┌─────────────────────────────────────────────────────┐
│  Berlinale 2026                     [Login Eventim] │
├─────────────────────────────────────────────────────┤
│  Today On Sale │ All Films │ Feb 12 │ ... │ Feb 22  │
│  🔍 Search films by title...                        │
├─────────────────────────────────────────────────────┤
│  ● COMPETITION                                      │
│  ┌───────────────────────────────────────────────┐  │
│  │ Dust                              Dir: Blondé │  │
│  │ Sun Feb 15 · 21:30 · Berlinale Palast         │  │
│  │ [SOLD OUT]                          [Watch]   │  │
│  │ Mon Feb 16 · 18:45 · Music Hall               │  │
│  │ [AVAILABLE]            [Buy Now] [Schedule]   │  │
│  └───────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────┐  │
│  │ Rose                            Dir: Abbasi   │  │
│  │ Sale in 2h 15m 30s                            │  │
│  │ [PENDING]                       [Schedule]    │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

</div>

## Prerequisites

You need a free **[Eventim.de](https://www.eventim.de)** account to purchase tickets:

1. Go to [eventim.de/myAccount](https://www.eventim.de/myAccount) and create an account (or use an existing one)
2. Add your **payment method** (credit card / PayPal / SEPA) in your Eventim account settings
3. That's it &mdash; no Berlinale account needed, no API keys, no configuration files

> **Note:** This tool does NOT store your Eventim credentials. It opens a real browser window where you log in manually. Your session is saved locally in `data/browser_profile/` (git-ignored) and persists across restarts.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Rswcf/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Run
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** &rarr; Click **Login Eventim** &rarr; Sign in with your Eventim account &rarr; Browse films &rarr; Click **Schedule Grab**.

> **macOS:** Double-click `Start Berlinale.command` in Finder for one-click launch.

## How It Works

```
  You pick films          App waits            10:00:00 CET
       │                     │                      │
       ▼                     ▼                      ▼
  ┌─────────┐         ┌───────────┐          ┌───────────┐
  │ Browse  │────────►│ Schedule  │─────────►│   GRAB!   │
  │ Films   │         │ & Preheat │          │ Add to    │
  └─────────┘         └───────────┘          │ Cart      │
       │                                     └─────┬─────┘
       │              ┌───────────┐                │
       └─────────────►│  Watch    │◄───────────────┘
        (sold out)    │  & Poll   │   (if failed,
                      └───────────┘    keep trying)
```

### Grab Flow (Browser Mode)

1. **T-60s** &mdash; Launch browser, load Eventim session
2. **T-30s** &mdash; Navigate to event page, dismiss cookie banner
3. **T-0s** &mdash; Refresh page, set quantity, click "Add to Cart"
4. **Retry** &mdash; Up to 3 attempts with 2s delay on failure

### Watch Flow (Sold-out Screenings)

1. Poll `/10am/10am_ticket_en.js` every 15s (5s in golden hour)
2. Detect `sold_out` &rarr; `available` transition
3. Extract new Eventim URL
4. Auto-trigger grab immediately

## Architecture

```
Frontend (Vanilla JS)        Backend (FastAPI)              External
┌──────────────┐    REST    ┌──────────────────┐    HTTP    ┌─────────────────┐
│ index.html   │◄──────────►│ main.py          │◄─────────►│ Berlinale API   │
│ app.js       │  WebSocket │ berlinale_api.py │           │ 344+ films      │
│ style.css    │◄──────────►│ scheduler.py     │           │ 1087 tickets    │
└──────────────┘            │ monitor.py       │           └─────────────────┘
                            │ grabber.py       │  Playwright  ┌──────────────┐
                            │ storage.py       │◄────────────►│ Eventim.de   │
                            └──────────────────┘   Browser    └──────────────┘
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/programme` | Full programme (all films, all days) |
| `GET` | `/api/programme/{day}` | Programme for a specific date |
| `GET` | `/api/today-on-sale` | Films on sale today |
| `GET` | `/api/ticket-status` | Real-time ticket status for all screenings |
| `GET` | `/api/tasks` | List all grab tasks |
| `POST` | `/api/tasks` | Create a grab/watch task |
| `DELETE` | `/api/tasks/{id}` | Cancel a task |
| `POST` | `/api/tasks/{id}/run` | Trigger immediate grab |
| `POST` | `/api/browser/login` | Open Eventim login page |
| `GET` | `/api/browser/status` | Check browser session |
| `WS` | `/ws/status` | Real-time updates (ticket status, task progress) |

## Configuration

All settings are in `app/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `SALE_ADVANCE_DAYS` | `3` | Days before screening that tickets go on sale |
| `SALE_TIME_HOUR` | `10` | Sale time (10:00 CET) |
| `GRAB_RETRY_COUNT` | `3` | Retry attempts per grab |
| `PRE_SALE_WARMUP` | `60` | Seconds before sale to start browser |
| `PRE_SALE_OPEN_PAGE` | `30` | Seconds before sale to open event page |
| `MONITOR_POLL_INTERVAL` | `15` | Seconds between ticket status polls |
| `MONITOR_FAST_POLL_INTERVAL` | `5` | Poll interval during golden hour |
| `MONITOR_GOLDEN_HOUR_MINUTES` | `60` | Minutes before screening = golden hour |

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.9+, FastAPI, uvicorn |
| Browser Automation | Playwright (persistent Chromium context) |
| Scheduling | APScheduler (async, Europe/Berlin timezone) |
| HTTP Client | httpx (async) |
| Data Models | Pydantic v2 |
| Frontend | Vanilla JS, CSS (dark theme) |
| Data Storage | JSON file-based |

## Tips for Best Results

- **Log into Eventim early** &mdash; The browser session persists, so log in once and keep the server running
- **Schedule grabs the night before** &mdash; Pick your films, set up tasks, go to sleep
- **Use Watch mode for sold-out films** &mdash; Tickets frequently return 30-60 min before screenings
- **Max 2 tickets per screening** &mdash; Eventim enforces this (5 for Generation section)
- **Keep the browser visible** &mdash; Runs in non-headless mode to avoid detection

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Browser won't start | Delete `data/browser_profile/SingletonLock` |
| "Not connected" status | Click "Login Eventim" and sign in |
| Grab fails immediately | Check if Eventim session expired, re-login |
| No films showing | Check your internet connection; Berlinale API may be down |
| Wrong sale times | Ensure system timezone is correct (uses Europe/Berlin) |

## Disclaimer

This tool is for personal use to help festival-goers purchase tickets. Please use responsibly and in accordance with Berlinale and Eventim terms of service. The authors are not responsible for any misuse.

## License

MIT

---

<details>
<summary><h2 id="中文">🇨🇳 中文</h2></summary>

# Berlinale 抢票器

**柏林国际电影节自动抢票工具**

柏林电影节的票在放映前3天的上午10:00（柏林时间）准时开售，热门电影几秒内售罄。本工具：

- **浏览全部节目** &mdash; 340+ 部电影，25 个板块，支持搜索和按日期筛选
- **实时票态监控** &mdash; WebSocket 推送，一目了然：可购 / 待售 / 售罄
- **精准定时抢票** &mdash; 提前预热浏览器，精确到秒发起购票
- **售罄监控** &mdash; 每 5-15 秒轮询，退票瞬间自动抢
- **持久会话** &mdash; Eventim 登录一次，重启不丢失

### 快速开始

```bash
git clone https://github.com/Rswcf/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer
pip install -r requirements.txt
playwright install chromium
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开 **http://localhost:8000** &rarr; 点击 **Login Eventim** 登录 &rarr; 浏览电影 &rarr; 点击 **Schedule Grab** 设置抢票任务。

### 使用技巧

- 提前一晚登录 Eventim 并设置好任务
- 售罄的电影用 Watch 模式，开场前 30-60 分钟经常有退票
- 每场最多购买 2 张票（Generation 板块最多 5 张）

</details>

<details>
<summary><h2 id="français">🇫🇷 Fran&ccedil;ais</h2></summary>

# Berlinale Ticket Buyer

**Outil d'achat automatique de billets pour le Festival International du Film de Berlin**

Les billets de la Berlinale sont mis en vente **3 jours avant chaque projection &agrave; 10h00 CET**. Les films populaires sont &eacute;puis&eacute;s en quelques secondes. Cet outil :

- **Parcourir le programme complet** &mdash; 340+ films dans 25 sections, recherche par titre, filtre par date
- **Statut des billets en temps r&eacute;el** &mdash; Mises &agrave; jour via WebSocket : disponible / en attente / &eacute;puis&eacute;
- **Achat programm&eacute; avec pr&eacute;cision** &mdash; Pr&eacute;chauffe le navigateur, ouvre la page 30s avant, rafra&icirc;chit &agrave; la seconde exacte
- **Surveillance des &eacute;puis&eacute;s** &mdash; Sondage toutes les 5-15s, achat automatique d&egrave;s qu'un billet redevient disponible
- **Session persistante** &mdash; Connectez-vous &agrave; Eventim une seule fois

### D&eacute;marrage rapide

```bash
git clone https://github.com/Rswcf/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer
pip install -r requirements.txt
playwright install chromium
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ouvrez **http://localhost:8000** &rarr; Cliquez sur **Login Eventim** &rarr; Connectez-vous &rarr; Parcourez les films &rarr; Cliquez sur **Schedule Grab**.

### Conseils

- Connectez-vous &agrave; Eventim la veille et programmez vos t&acirc;ches
- Utilisez le mode Watch pour les films complets &mdash; des billets reviennent souvent 30-60 min avant la projection
- Maximum 2 billets par projection (5 pour la section Generation)

</details>

<details>
<summary><h2 id="deutsch">🇩🇪 Deutsch</h2></summary>

# Berlinale Ticket Buyer

**Automatisches Ticket-Tool f&uuml;r die Internationalen Filmfestspiele Berlin**

Berlinale-Tickets gehen **3 Tage vor der Vorstellung um 10:00 Uhr MEZ** in den Verkauf. Beliebte Filme sind in Sekunden ausverkauft. Dieses Tool:

- **Gesamtes Programm durchsuchen** &mdash; 340+ Filme in 25 Sektionen, Titelsuche, Datumsfilter
- **Echtzeit-Ticketstatus** &mdash; Live-Updates via WebSocket: verf&uuml;gbar / ausstehend / ausverkauft
- **Pr&auml;ziser Ticketkauf** &mdash; Browser wird vorgeheizt, Seite 30s vorher ge&ouml;ffnet, exakter Refresh zur Verkaufszeit
- **Ausverkauft-&Uuml;berwachung** &mdash; Abfrage alle 5-15s, automatischer Kauf bei R&uuml;ckgaben
- **Persistente Sitzung** &mdash; Einmal bei Eventim anmelden, bleibt &uuml;ber Neustarts erhalten

### Schnellstart

```bash
git clone https://github.com/Rswcf/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer
pip install -r requirements.txt
playwright install chromium
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

&Ouml;ffnen Sie **http://localhost:8000** &rarr; Klicken Sie auf **Login Eventim** &rarr; Anmelden &rarr; Filme durchsuchen &rarr; **Schedule Grab** klicken.

### Tipps

- Melden Sie sich abends vorher bei Eventim an und richten Sie Aufgaben ein
- Nutzen Sie den Watch-Modus f&uuml;r ausverkaufte Filme &mdash; 30-60 Min. vor Vorstellungsbeginn werden oft Tickets zur&uuml;ckgegeben
- Maximal 2 Tickets pro Vorstellung (5 f&uuml;r die Sektion Generation)

</details>

<details>
<summary><h2 id="español">🇪🇸 Espa&ntilde;ol</h2></summary>

# Berlinale Ticket Buyer

**Herramienta automatizada de compra de entradas para el Festival Internacional de Cine de Berl&iacute;n**

Las entradas de la Berlinale salen a la venta **3 d&iacute;as antes de cada proyecci&oacute;n a las 10:00 CET**. Las pel&iacute;culas populares se agotan en segundos. Esta herramienta:

- **Explorar el programa completo** &mdash; 340+ pel&iacute;culas en 25 secciones, b&uacute;squeda por t&iacute;tulo, filtro por fecha
- **Estado de entradas en tiempo real** &mdash; Actualizaciones via WebSocket: disponible / pendiente / agotado
- **Compra programada con precisi&oacute;n** &mdash; Precalienta el navegador, abre la p&aacute;gina 30s antes, refresca en el segundo exacto
- **Vigilancia de agotados** &mdash; Consulta cada 5-15s, compra autom&aacute;tica cuando vuelven entradas
- **Sesi&oacute;n persistente** &mdash; Inicia sesi&oacute;n en Eventim una sola vez

### Inicio r&aacute;pido

```bash
git clone https://github.com/Rswcf/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer
pip install -r requirements.txt
playwright install chromium
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abra **http://localhost:8000** &rarr; Haga clic en **Login Eventim** &rarr; Inicie sesi&oacute;n &rarr; Explore pel&iacute;culas &rarr; Haga clic en **Schedule Grab**.

### Consejos

- Inicie sesi&oacute;n en Eventim la noche anterior y programe sus tareas
- Use el modo Watch para pel&iacute;culas agotadas &mdash; suelen aparecer entradas 30-60 min antes de la proyecci&oacute;n
- M&aacute;ximo 2 entradas por proyecci&oacute;n (5 para la secci&oacute;n Generation)

</details>

<details>
<summary><h2 id="português">🇧🇷 Portugu&ecirc;s</h2></summary>

# Berlinale Ticket Buyer

**Ferramenta automatizada de compra de ingressos para o Festival Internacional de Cinema de Berlim**

Os ingressos da Berlinale entram &agrave; venda **3 dias antes de cada exibi&ccedil;&atilde;o &agrave;s 10:00 CET**. Filmes populares esgotam em segundos. Esta ferramenta:

- **Navegar pelo programa completo** &mdash; 340+ filmes em 25 se&ccedil;&otilde;es, busca por t&iacute;tulo, filtro por data
- **Status dos ingressos em tempo real** &mdash; Atualiza&ccedil;&otilde;es via WebSocket: dispon&iacute;vel / pendente / esgotado
- **Compra agendada com precis&atilde;o** &mdash; Pr&eacute;-aquece o navegador, abre a p&aacute;gina 30s antes, atualiza no segundo exato
- **Monitoramento de esgotados** &mdash; Consulta a cada 5-15s, compra autom&aacute;tica quando ingressos retornam
- **Sess&atilde;o persistente** &mdash; Fa&ccedil;a login no Eventim uma &uacute;nica vez

### In&iacute;cio r&aacute;pido

```bash
git clone https://github.com/Rswcf/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer
pip install -r requirements.txt
playwright install chromium
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abra **http://localhost:8000** &rarr; Clique em **Login Eventim** &rarr; Fa&ccedil;a login &rarr; Navegue pelos filmes &rarr; Clique em **Schedule Grab**.

### Dicas

- Fa&ccedil;a login no Eventim na noite anterior e programe suas tarefas
- Use o modo Watch para filmes esgotados &mdash; ingressos frequentemente retornam 30-60 min antes da exibi&ccedil;&atilde;o
- M&aacute;ximo de 2 ingressos por exibi&ccedil;&atilde;o (5 para a se&ccedil;&atilde;o Generation)

</details>

<details>
<summary><h2 id="日本語">🇯🇵 日本語</h2></summary>

# Berlinale Ticket Buyer

**ベルリン国際映画祭の自動チケット購入ツール**

ベルリナーレのチケットは**上映3日前の中央ヨーロッパ時間10:00に発売**されます。人気作品は数秒で売り切れます。このツールは：

- **全プログラム閲覧** &mdash; 25セクション、340作品以上をタイトル検索・日付フィルター付きで閲覧
- **リアルタイムチケット状況** &mdash; WebSocket経由のライブ更新：購入可能 / 発売前 / 売り切れ
- **精密な購入スケジューリング** &mdash; ブラウザを事前起動、30秒前にページを開き、発売の瞬間にリフレッシュ
- **売り切れ監視** &mdash; 5-15秒ごとにポーリング、チケットが戻った瞬間に自動購入
- **永続セッション** &mdash; Eventimに一度ログインすれば再起動後も有効

### クイックスタート

```bash
git clone https://github.com/Rswcf/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer
pip install -r requirements.txt
playwright install chromium
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**http://localhost:8000** を開く &rarr; **Login Eventim** をクリック &rarr; ログイン &rarr; 映画を閲覧 &rarr; **Schedule Grab** をクリック。

### ヒント

- 前日の夜にEventimにログインしてタスクを設定
- 売り切れの映画にはWatchモードを使用 &mdash; 上映30-60分前にチケットが戻ることが多い
- 1上映につき最大2枚（Generationセクションは5枚）

</details>

<details>
<summary><h2 id="한국어">🇰🇷 한국어</h2></summary>

# Berlinale Ticket Buyer

**베를린 국제영화제 자동 티켓 구매 도구**

베를리날레 티켓은 **상영 3일 전 중앙유럽시간 10:00에 판매 시작**됩니다. 인기 영화는 몇 초 만에 매진됩니다. 이 도구는:

- **전체 프로그램 탐색** &mdash; 25개 섹션, 340편 이상의 영화를 제목 검색 및 날짜 필터로 탐색
- **실시간 티켓 상태** &mdash; WebSocket을 통한 실시간 업데이트: 구매 가능 / 대기 중 / 매진
- **정밀한 구매 스케줄링** &mdash; 브라우저 사전 준비, 30초 전 페이지 오픈, 판매 시작 정각에 새로고침
- **매진 모니터링** &mdash; 5-15초 간격 폴링, 티켓 반환 즉시 자동 구매
- **영구 세션** &mdash; Eventim 한 번 로그인으로 재시작 후에도 유지

### 빠른 시작

```bash
git clone https://github.com/Rswcf/berlinale-ticket-buyer.git
cd berlinale-ticket-buyer
pip install -r requirements.txt
playwright install chromium
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**http://localhost:8000** 열기 &rarr; **Login Eventim** 클릭 &rarr; 로그인 &rarr; 영화 탐색 &rarr; **Schedule Grab** 클릭.

### 팁

- 전날 밤에 Eventim에 로그인하고 작업을 설정하세요
- 매진된 영화에는 Watch 모드를 사용하세요 &mdash; 상영 30-60분 전에 티켓이 자주 반환됩니다
- 상영당 최대 2매 구매 가능 (Generation 섹션은 5매)

</details>

---

<div align="center">

**If this tool helped you get Berlinale tickets, consider giving it a star!**

Made with late nights and love for cinema.

</div>
