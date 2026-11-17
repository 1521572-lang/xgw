# Источники оформления веб-обзора zapret2

Оформление адаптировано из StressOzz/Zapret-Manager, коммит
`1ff3f5aa01e85125548eccc0a1dd6229a99123fb`. Исходный
[ZapretManager_LuCI.sh](https://github.com/StressOzz/Zapret-Manager/blob/1ff3f5aa01e85125548eccc0a1dd6229a99123fb/ZapretManager_LuCI.sh)
прочитан как текст. Его SHA-256
`10c4839e85985ba9916c36ab090ddc2bd3db308fbf5a97ef1331c02afff0b59a`.

| Источник в upstream | Использованная часть | Адаптация в XGW |
|---|---|---|
| `/www/luci-static/resources/view/zapret-manager/style.css` в установщике | `.zm-cards`, `.zm-card` | Сетка и форма карточек, переменные и типографика XGW, защита от переполнения на узких экранах |
| `/www/zm/app.css` в установщике | `.zmw-shell`, `.zmw-side`, `.zmw-nav` | Боковая навигация и мобильная раскладка на CSS XGW |
| `/www/zm/app.js`, `/www/zm-webui.html` в установщике | Сопоставлены структура страниц и навигация | HTML и JavaScript написаны для HTTP API XGW без переноса RPC и OpenWrt |

Изменённые правила помечены в [zapret2.css](../../src/xgw/ui/zapret2.css).
[LICENSE Apache-2.0](../../src/xgw/ui/zapret2.LICENSE.txt) и
[NOTICE StressOzz](../../src/xgw/ui/zapret2.NOTICE.txt) входят в ресурсы пакета.
SHA-256 оригиналов:

- LICENSE `43070e2d4e532684de521b885f385d0841030efa2b1a20bafb76133a5e1379c1`
- NOTICE `a6e1784f8a4b9ac166d5f16b0792f065a429855605d87eb5626c1fe4df166bd0`

Иконка XGW, системные шрифты и цвета принадлежат существующей теме XGW.
Из upstream использовано оформление, остальная схема доступа и управления
остаётся за HTTP-сервером XGW.
