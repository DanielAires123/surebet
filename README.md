# SureBet Monitor

Monitorização automática da tua conta [pt.surebet.com](https://pt.surebet.com) com **Playwright + Chromium**.  
Extrai Valuebets / Surebets dos presets guardados, valida a matemática, deduplica e envia alertas **Telegram**.

**Não** faz apostas. **Não** contorna CAPTCHA / Cloudflare. **Não** usa API SureBet.

## O que faz

A cada ~15 minutos (GitHub Actions):

1. Abre 1 Chromium headless  
2. Faz 1 login  
3. Para cada filtro em `filters.json`: abre `/surebets` ou `/valuebets`, seleciona o preset (`#filter_current_id`), espera resultados, faz parse do DOM  
4. Normaliza → valida → deduplica → Telegram (± screenshot)  
5. Guarda `state.json` na branch `bot-state`

Filtros default:

| Filtro | Tipo | Threshold |
|---|---|---|
| Surebets | surebet | lucro ≥ 1% |
| 0.5UN / 0.7UN / 1UN / MAX | valuebet | overvalue ≥ 5% |

## Setup rápido

### 1. Repositório

1. Cria um repo no GitHub  
2. Faz push deste código para `main`

### 2. Telegram

1. No Telegram, fala com [@BotFather](https://t.me/BotFather) → `/newbot`  
2. Copia o **TELEGRAM_BOT_TOKEN**  
3. Envia uma mensagem ao teu bot  
4. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` e copia o **chat.id** → **TELEGRAM_CHAT_ID**  
   (ou usa um canal/grupo onde o bot seja admin)

### 3. Secrets no GitHub

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valor |
|---|---|
| `SUREBET_USERNAME` | email SureBet |
| `SUREBET_PASSWORD` | password SureBet |
| `TELEGRAM_BOT_TOKEN` | token BotFather |
| `TELEGRAM_CHAT_ID` | id do chat |

Nunca commits estes valores.

### 4. Configurar filtros

Edita `filters.json`. Cada filtro precisa de `surebet_filter_id` (o `value` do `<option>` no dropdown "Filtro" no site).

Para descobrir o ID: DevTools → `#filter_current_id` → `<option value="...">Nome</option>`.

### 5. Correr no Actions

1. **Actions → surebet-monitor → Run workflow**  
2. Primeiro teste: `dry_run=true`  
3. Ou com input vazio para run normal  
4. Para testar Telegram só: workflow local `python main.py --test-telegram` (com secrets no `.env`)

### 6. Local (opcional)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
# preenche .env
pytest -q
python main.py --test-telegram
python main.py --dry-run --filter valuebet_05un
python main.py --dry-run --headed --debug
```

### 7. Ativar schedule

O cron `7,22,37,52 * * * *` já está no workflow (~15 em 15 min).  
Confirma que Actions estão enabled no repo.

## CLI

```text
python main.py
python main.py --dry-run
python main.py --debug
python main.py --filter valuebet_05un
python main.py --test-telegram
python main.py --headed
```

## Branch bot-state

Runners são efémeros. O workflow grava só `state.json` (hashes / last odds / timestamps) na branch `bot-state`.  
**Sem** cookies, passwords ou `storage_state`.

## Validação

- **Valuebet:** `EV = odds × probability − 1`; compara com overvalue do site (tolerância 0.5pp)  
- **Arbitrage:** `Σ(1/odds) < 1 − ε` **e** mercados compatíveis (mesmo período/line/seleções complementares). Na dúvida → `unverified`

## Troubleshooting

| Sintoma | Causa / ação |
|---|---|
| **LOGIN FAILED** | Credenciais erradas ou formulário mudou (`surebet/auth.py` / `selectors.py`) |
| **CAPTCHA DETECTED** | Site pediu CAPTCHA — o monitor **para**. Não há bypass. Espera / login manual / reduz frequência |
| **ANTI_BOT_DETECTED** | Mesmo: para sem contornar |
| **SELECTOR NOT FOUND** | Layout mudou — atualiza `surebet/selectors.py` com DevTools |
| **FILTER NOT FOUND** | `surebet_filter_id` inválido ou preset apagado na conta |
| **RESULTS TIMEOUT** | Tabela não estabilizou a tempo — rede lenta ou filtro a carregar |
| **PARSER HEALTH / LAYOUT CHANGED** | Há rows no DOM mas o parse falhou em massa — selectors desatualizados |
| **TELEGRAM ERROR** | Token/chat errados, bot sem acesso ao chat, ou rate limit |
| **BOT-STATE ERROR** | Permissões `contents: write` / branch protegida |

## Segurança

- Sem stealth plugins, fingerprint spoofing, CAPTCHA solvers, proxy rotation anti-ban  
- Screenshots só para Telegram/debug e são apagados após envio  
- `.env` está no `.gitignore`

## Estrutura

Ver `docs/superpowers/specs/2026-09-29-surebet-monitor-design.md` e o plano em `docs/superpowers/plans/`.
