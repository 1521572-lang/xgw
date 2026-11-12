# Происхождение ассетов

Файлы этого каталога получены из открытого репозитория `github.com/ProtonVPN/win-app`
(Proton AG), лицензия — GNU General Public License v3.0.

| Каталог | Источник в репозитории | Что сделано |
|---|---|---|
| `icons/` | `ProtonVPN.Client.Common.UI/Assets/Icons/PathIcons/*.cs` (геометрия `IconGeometry16/20/24/32`) | геометрия записана как SVG с `fill="currentColor"` и `fill-rule="evenodd"` |
| `flags/` | `ProtonVPN.Client.Common.UI/Assets/Flags/*.svg` | без изменений |
| `illustrations/` | `ProtonVPN.Client.Common.UI/Assets/Illustrations/{Dark,Light}/*.png` | без изменений, девять файлов на тему |
| `world-map.svg` | `ProtonVPN.Client.Common.UI/Assets/Illustrations/world-map.svg` | без изменений (перекрашивается при загрузке) |
| `map_points.json` | вычислено из `world-map.svg` | середины рамок стран для отметок на карте |

Название «Proton VPN», логотип и фирменные иллюстрации тарифов в пакет не включены
и в окне не используются: это товарные знаки Proton AG, лицензия GPL на них не
распространяется.

Следствие лицензии: пакет, распространяемый вместе с этими файлами, должен
распространяться на условиях GPL-3.0 с сохранением этого уведомления. Чтобы снять
это условие, каталог `assets/` нужно заменить собственными файлами с теми же именами.
