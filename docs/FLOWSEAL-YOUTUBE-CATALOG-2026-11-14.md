# Каталог исходных методов Flowseal для проверки в XGW

Закреплён `2401b7a13837139b0265632464ba563dddbf80d8`, метка выпуска `1.10.4`.
Прочитаны 22 BAT как текст. Их выполнение и установка WinDivert не производились.
Списки и данные проверены по Git blob SHA-1 закреплённого дерева, дополнительно вычислен SHA-256.
Полные параметры, порядок профилей, ссылки, размеры и суммы — в [машинном каталоге](helpers/flowseal-youtube-source.json).
Это каталог источника, не готовые аргументы nfqws2 и не результат живой проверки.

| Конфигурация | Профили в исходном порядке |
|---|---|
| general (ALT).bat | 1: Q01, 4: G01, 5: H01, 6: I01, 7: S01 |
| general (ALT10).bat | 1: Q01, 4: G02, 5: H02, 6: I01, 7: S02 |
| general (ALT11).bat | 1: Q02, 4: G03, 5: H03, 6: I02, 7: S03 |
| general (ALT12).bat | 1: Q02, 4: G04, 5: H04, 6: I02, 7: S04 |
| general (ALT13).bat | 1: Q02, 4: G05, 5: H05, 6: I02, 7: S05 |
| general (ALT2).bat | 1: Q01, 4: G06, 5: H06, 6: I01, 7: S06 |
| general (ALT3).bat | 1: Q01, 4: G07, 5: H07, 6: I01, 7: S07 |
| general (ALT4).bat | 1: Q01, 4: G08, 5: H08, 6: I01, 7: S08 |
| general (ALT5).bat | 1: Q01, 3: S09, 5: I01 |
| general (ALT6).bat | 1: Q01, 4: G09, 5: H09, 6: I01, 7: S10 |
| general (ALT7).bat | 1: Q01, 4: G10, 5: H10, 6: I01, 7: S11 |
| general (ALT8).bat | 1: Q01, 4: G11, 5: H11, 6: I01, 7: S12 |
| general (ALT9).bat | 1: Q01, 4: G12, 5: H12, 6: I01, 7: S13 |
| general (EXP).bat | 1: Q03, 4: G04, 5: H13, 6: I02, 7: S14 |
| general (FAKE TLS AUTO ALT).bat | 1: Q02, 4: G13, 5: H14, 6: I02, 7: S15 |
| general (FAKE TLS AUTO ALT2).bat | 1: Q02, 4: G14, 5: H15, 6: I02, 7: S16 |
| general (FAKE TLS AUTO ALT3).bat | 1: Q02, 4: G15, 5: H16, 6: I02, 7: S17 |
| general (FAKE TLS AUTO).bat | 1: Q02, 4: G16, 5: H17, 6: I02, 7: S18 |
| general (SIMPLE FAKE ALT).bat | 1: Q01, 4: G17, 5: H18, 6: I01, 7: S19 |
| general (SIMPLE FAKE ALT2).bat | 1: Q01, 4: G02, 5: H19, 6: I01, 7: S20 |
| general (SIMPLE FAKE).bat | 1: Q01, 4: G04, 5: H20, 6: I01, 7: S21 |
| general.bat | 1: Q01, 4: G09, 5: H21, 6: I01, 7: S22 |

## Уникальные группы

G — TCP списка Google, H — общий TCP, Q — QUIC по hostlist, I — QUIC по ipset, S — прочий TCP/443 (включая ALT5 и запасные IPSet-профили).
Разные G требуют отдельных проверок. Совпадение G не означает равенства всей конфигурации.
H/Q/I/S нужны, когда фактический запрос попал в их фильтр; они не заменяют предшествующий G.

| Группа | Приём | Повторы | Дополнительные параметры |
|---|---|---|---|
| G01 | fake,fakedsplit | 6 | ip-id=zero, fooling=ts, fakedsplit-pattern=0x00, fake-tls=tls_clienthello_www_google_com.bin |
| G02 | fake | 6 | ip-id=zero, fooling=ts, fake-tls=tls_clienthello_www_google_com.bin |
| G03 | fake,multisplit | 8 | ip-id=zero, split-seqovl=681, split-pos=1, fooling=ts, split-seqovl-pattern=tls_clienthello_www_google_com.bin, fake-tls=tls_clienthello_www_google_com.bin |
| G04 | hostfakesplit | default: проверить | ip-id=zero, fooling=ts, hostfakesplit-mod=host=www.google.com |
| G05 | hostfakesplit | default: проверить | fooling=ts, hostfakesplit-mod=host=www.google.com |
| G06 | multisplit | default: проверить | ip-id=zero, split-seqovl=652, split-pos=2, split-seqovl-pattern=tls_clienthello_www_google_com.bin |
| G07 | fake,hostfakesplit | default: проверить | ip-id=zero, fake-tls-mod=rnd,dupsid,sni=www.google.com, hostfakesplit-mod=host=www.google.com,altorder=1, fooling=ts |
| G08 | fake,multisplit | 6 | ip-id=zero, fooling=badseq, badseq-increment=1000, fake-tls=tls_clienthello_www_google_com.bin |
| G09 | multisplit | default: проверить | ip-id=zero, split-seqovl=681, split-pos=1, split-seqovl-pattern=tls_clienthello_www_google_com.bin |
| G10 | multisplit | default: проверить | ip-id=zero, split-pos=2,sniext+1, split-seqovl=679, split-seqovl-pattern=tls_clienthello_www_google_com.bin |
| G11 | fake | 6 | ip-id=zero, fake-tls-mod=none, fooling=badseq, badseq-increment=2 |
| G12 | hostfakesplit | 4 | ip-id=zero, fooling=ts, hostfakesplit-mod=host=www.google.com |
| G13 | fake,fakedsplit | 8 | ip-id=zero, split-pos=1, fooling=badseq, badseq-increment=2, fake-tls-mod=rnd,dupsid,sni=www.google.com |
| G14 | fake,multisplit | 8 | ip-id=zero, split-seqovl=681, split-pos=1, fooling=badseq, badseq-increment=10000000, split-seqovl-pattern=tls_clienthello_www_google_com.bin, fake-tls-mod=rnd,dupsid,sni=www.google.com |
| G15 | fake,multisplit | 8 | ip-id=zero, split-seqovl=681, split-pos=1, fooling=ts, split-seqovl-pattern=tls_clienthello_www_google_com.bin, fake-tls-mod=rnd,dupsid,sni=www.google.com |
| G16 | fake,multidisorder | 11 | ip-id=zero, split-pos=1,midsld, fooling=badseq, fake-tls=0x00000000, fake-tls=!, fake-tls-mod=rnd,dupsid,sni=www.google.com |
| G17 | fake | 6 | ip-id=zero, fooling=badseq, badseq-increment=2, fake-tls=tls_clienthello_www_google_com.bin |
| H01 | fake,fakedsplit | 6 | fooling=ts, fakedsplit-pattern=0x00, fake-tls=stun.bin, fake-tls=tls_clienthello_www_google_com.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H02 | fake | 6 | fooling=ts, fake-tls=stun.bin, fake-tls=tls_clienthello_4pda_to.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H03 | fake,multisplit | 8 | split-seqovl=664, split-pos=1, fooling=ts, split-seqovl-pattern=tls_clienthello_www_sferum_ru.bin, fake-tls=stun2.bin, fake-tls=tls_clienthello_www_sferum_ru.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H04 | fake,multisplit | 8 | split-seqovl=664, split-pos=1, fooling=ts, split-seqovl-pattern=tls_clienthello_www_sferum_ru.bin, fake-tls=stun.bin, fake-tls=tls_clienthello_www_sferum_ru.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H05 | fake,hostfakesplit | 5 | fooling=ts, hostfakesplit-mod=host=mail.ru,altorder=1, fake-tls=tls_clienthello_sochi_park.bin, fake-tls=stun2.bin, fake-http=tls_clienthello_sochi_park.bin |
| H06 | multisplit | default: проверить | split-seqovl=652, split-pos=2, split-seqovl-pattern=tls_clienthello_www_google_com.bin |
| H07 | fake,hostfakesplit | default: проверить | fake-tls-mod=rnd,dupsid,sni=ya.ru, hostfakesplit-mod=host=ya.ru,altorder=1, fooling=ts, fake-http=tls_clienthello_www_sferum_ru.bin |
| H08 | fake,multisplit | 6 | fooling=badseq, badseq-increment=1000, fake-tls=stun.bin, fake-tls=tls_clienthello_www_google_com.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H09 | multisplit | default: проверить | split-seqovl=681, split-pos=1, split-seqovl-pattern=tls_clienthello_www_google_com.bin |
| H10 | multisplit | default: проверить | split-pos=2,sniext+1, split-seqovl=679, split-seqovl-pattern=tls_clienthello_www_google_com.bin |
| H11 | fake | 6 | fake-tls-mod=none, fooling=badseq, badseq-increment=2, fake-http=tls_clienthello_www_sferum_ru.bin |
| H12 | hostfakesplit | 4 | fooling=ts,md5sig, hostfakesplit-mod=host=ozon.ru |
| H13 | fake,multisplit | 4 | split-seqovl=480, split-pos=1, fooling=ts, split-seqovl-pattern=stun2.bin, fake-tls=tls_clienthello_www_sferum_ru.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H14 | fake,fakedsplit | 8 | split-pos=1, fooling=badseq, badseq-increment=2, fake-tls-mod=rnd,dupsid,sni=www.google.com, fake-http=tls_clienthello_www_sferum_ru.bin |
| H15 | fake,multisplit | 8 | split-seqovl=681, split-pos=1, fooling=badseq, badseq-increment=10000000, split-seqovl-pattern=tls_clienthello_www_google_com.bin, fake-tls-mod=rnd,dupsid,sni=www.google.com, fake-http=tls_clienthello_www_sferum_ru.bin |
| H16 | fake,multisplit | 8 | split-seqovl=681, split-pos=1, fooling=ts, split-seqovl-pattern=tls_clienthello_www_google_com.bin, fake-tls-mod=rnd,dupsid,sni=www.google.com, fake-http=tls_clienthello_www_sferum_ru.bin |
| H17 | fake,multidisorder | 11 | split-pos=1,midsld, fooling=badseq, fake-tls=0x00000000, fake-tls=!, fake-tls-mod=rnd,dupsid,sni=www.google.com, fake-http=tls_clienthello_www_sferum_ru.bin |
| H18 | fake | 6 | fooling=badseq, badseq-increment=2, fake-tls=stun2.bin, fake-tls=tls_clienthello_www_google_com.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H19 | fake | 6 | fooling=ts, fake-tls=stun2.bin, fake-tls=tls_clienthello_www_sferum_ru.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H20 | fake | 6 | fooling=ts, fake-tls=tls_clienthello_www_google_com.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| H21 | multisplit | default: проверить | split-seqovl=568, split-pos=1, split-seqovl-pattern=tls_clienthello_4pda_to.bin |
| I01 | fake | 6 | fake-quic=quic_initial_www_google_com.bin |
| I02 | fake | 11 | fake-quic=quic_initial_www_google_com.bin |
| Q01 | fake | 6 | fake-quic=quic_initial_www_google_com.bin |
| Q02 | fake | 11 | fake-quic=quic_initial_www_google_com.bin |
| Q03 | fake | 11 | fake-quic=quic_initial_www_google_com.bin |
| S01 | fake,fakedsplit | 6 | fooling=ts, fakedsplit-pattern=0x00, fake-tls=stun.bin, fake-tls=tls_clienthello_www_google_com.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S02 | fake | 6 | fooling=ts, fake-tls=stun.bin, fake-tls=tls_clienthello_4pda_to.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S03 | fake,multisplit | 8 | split-seqovl=664, split-pos=1, fooling=ts, split-seqovl-pattern=tls_clienthello_www_sferum_ru.bin, fake-tls=stun2.bin, fake-tls=tls_clienthello_www_sferum_ru.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S04 | fake,multisplit | 8 | split-seqovl=664, split-pos=1, fooling=ts, split-seqovl-pattern=tls_clienthello_www_sferum_ru.bin, fake-tls=stun.bin, fake-tls=tls_clienthello_www_sferum_ru.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S05 | fake,hostfakesplit | 5 | fooling=ts, hostfakesplit-mod=host=mail.ru,altorder=1, fake-tls=tls_clienthello_sochi_park.bin, fake-tls=stun2.bin, fake-http=tls_clienthello_sochi_park.bin |
| S06 | multisplit | default: проверить | split-seqovl=652, split-pos=2, split-seqovl-pattern=tls_clienthello_www_google_com.bin |
| S07 | fake,hostfakesplit | default: проверить | fake-tls-mod=rnd,dupsid,sni=ya.ru, hostfakesplit-mod=host=ya.ru,altorder=1, fooling=ts, fake-http=tls_clienthello_www_sferum_ru.bin |
| S08 | fake,multisplit | 6 | fooling=badseq, badseq-increment=1000, fake-tls=stun.bin, fake-tls=tls_clienthello_www_google_com.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S09 | syndata,multidisorder | default: проверить |  |
| S10 | multisplit | default: проверить | split-seqovl=681, split-pos=1, split-seqovl-pattern=tls_clienthello_www_google_com.bin |
| S11 | syndata | default: проверить |  |
| S12 | fake | 6 | fake-tls-mod=none, fooling=badseq, badseq-increment=2, fake-http=tls_clienthello_www_sferum_ru.bin |
| S13 | hostfakesplit | 4 | fooling=ts, hostfakesplit-mod=host=ozon.ru |
| S14 | fake,multisplit | 4 | split-seqovl=480, split-pos=1, fooling=ts, split-seqovl-pattern=stun2.bin, fake-tls=tls_clienthello_www_sferum_ru.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S15 | fake,fakedsplit | 8 | split-pos=1, fooling=badseq, badseq-increment=2, fake-tls-mod=rnd,dupsid,sni=www.google.com, fake-http=tls_clienthello_www_sferum_ru.bin |
| S16 | fake,multisplit | 8 | split-seqovl=681, split-pos=1, fooling=badseq, badseq-increment=10000000, split-seqovl-pattern=tls_clienthello_www_google_com.bin, fake-tls-mod=rnd,dupsid,sni=www.google.com, fake-http=tls_clienthello_www_sferum_ru.bin |
| S17 | fake,multisplit | 8 | split-seqovl=681, split-pos=1, fooling=ts, split-seqovl-pattern=tls_clienthello_www_google_com.bin, fake-tls-mod=rnd,dupsid,sni=www.google.com, fake-http=tls_clienthello_www_sferum_ru.bin |
| S18 | fake,multidisorder | 11 | split-pos=1,midsld, fooling=badseq, fake-tls=0x00000000, fake-tls=!, fake-tls-mod=rnd,dupsid,sni=www.google.com, fake-http=tls_clienthello_www_sferum_ru.bin |
| S19 | fake | 6 | fooling=badseq, badseq-increment=2, fake-tls=stun2.bin, fake-tls=tls_clienthello_www_google_com.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S20 | fake | 6 | fooling=ts, fake-tls=stun2.bin, fake-tls=tls_clienthello_www_sferum_ru.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S21 | fake | 6 | fooling=ts, fake-tls=tls_clienthello_www_google_com.bin, fake-http=tls_clienthello_www_sferum_ru.bin |
| S22 | multisplit | default: проверить | split-seqovl=568, split-pos=1, split-seqovl-pattern=tls_clienthello_4pda_to.bin |

## Ограничения сопоставления

- `youtube.com`, `googlevideo.com`, `youtubei.googleapis.com`, `youtube-nocookie.com` входят в list-google.txt.
- В штатном list-general.txt этих доменов нет. QUIC по общему hostlist не обязательно обслуживает YouTube.
- Общие списки могут содержать пользовательские дополнения; исходный эксперимент использует пустые user-списки.
- Приоритет G над H сохраняется. В ALT9 MD5 относится к H, Google-профиль использует timestamps.
- Группы строятся по явным опциям, отсутствующие значения требуют проверки default исходного winws.
- ALT5: S09 — IPv4 TCP без положительного hostlist/IPSet, syndata,multidisorder; не терять фазу SYN.
- EXP: профиль QUIC задаёт filter-l7=quic без filter-udp; это отдельная группа, не обычный UDP/443 фильтр.
- Все профили, включая игровые/Discord, и глобальные wf-фильтры сохранены в all_profiles_in_source_order/global_options.
  Игровые/Discord варианты не запускаются без фактического совпадения YouTube-потока с их фильтрами.
- service.bat зафиксирован как текст: GameFilter без настроек disabled (TCP/UDP=12), user-списки пустые.
- Данные .bin здесь не распространяются, их байты исполнитель получает по закреплённым URL и сверяет SHA-256.
- Git blob SHA-1 и SHA-256 — разные суммы; их поля нельзя взаимозаменять.
