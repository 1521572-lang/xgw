# Отчёт T0: снимок Tailscale на шлюзе (только чтение)

Программа: ветка tailscale-t0, 2990e6d. XGW: 0.1.15. Снимок: 2026-10-20 13:12:49.
Согласие заказчика: да. Tailscale установлен: да.

## Гипотезы
| # | Итог | Пояснение скрипта |
|---|---|---|
| К1 | подтверждена | подтверждена — в цепочке output нет исключения для метки Tailscale 0x80000, правило meta mark set затирает её |
| К2 | подтверждена | подтверждена — DNS к 100.100.100.100:53 перехватывается в Xray (исключения для tailscale0 нет); имя устройства через resolved: не разрешилось |
| К3 | нет данных | нет данных — шлюз сейчас не в режиме blocked (цепочки block_output нет); проявляется только в нём |
| К4 | подтверждена | подтверждена — v6_guard отбивает IPv6 tailnet (fd7a:…) и IPv6-сокеты tailscaled: исключений нет |
| К5 (доп.) | нет | нет — адрес WAN не из 100.64.0.0/10 |
| К6 (доп.) | нет | нет — tailscale0 не DNS по умолчанию |

## Состояние
```text
tailscaled: active
версия: 1.104.1
BackendState: Running
адреса tailnet: 100.x.y.1, fd7a:…:1
в сети: True; DERP: par
устройств в tailnet: 5, в сети: 1
MagicDNS: True
Health: пусто
prefs NetfilterMode: 2
prefs CorpDNS: true
prefs RouteAll: false
prefs ExitNodeID: ""
prefs RunSSH: false
prefs ShieldsUp: false
prefs WantRunning: true
prefs LoggedOut: false
netcheck UDP: true
netcheck IPv4: yes, внешний-IP-1:50789
netcheck IPv6: no, but OS has support
netcheck MappingVariesByDestIP: false
netcheck Nearest DERP: Frankfurt
ip rule Tailscale (5210/5230/5250/5270): 5210, 5230, 5250, 5270
ip rule XGW (90/95/100): 95, 100
таблица 52: маршрутов 5
интерфейс tailscale0: есть
цепочки Tailscale в nft: ts-forward, ts-input, ts-postrouting
таблицы nft: ip xgw, ip6 xgw6, ip nat, ip filter, ip6 nat, ip6 filter, ip mangle, ip6 mangle
```

## Файлы снимка (маскированные)
### summary.txt
```text
== Состояние ==
tailscaled: active
версия: 1.104.1
BackendState: Running
адреса tailnet: 100.x.y.1, fd7a:…:1
в сети: True; DERP: par
устройств в tailnet: 5, в сети: 1
MagicDNS: True
Health: пусто
prefs NetfilterMode: 2
prefs CorpDNS: true
prefs RouteAll: false
prefs ExitNodeID: ""
prefs RunSSH: false
prefs ShieldsUp: false
prefs WantRunning: true
prefs LoggedOut: false
netcheck UDP: true
netcheck IPv4: yes, внешний-IP-1:50789
netcheck IPv6: no, but OS has support
netcheck MappingVariesByDestIP: false
netcheck Nearest DERP: Frankfurt
ip rule Tailscale (5210/5230/5250/5270): 5210, 5230, 5250, 5270
ip rule XGW (90/95/100): 95, 100
таблица 52: маршрутов 5
интерфейс tailscale0: есть
цепочки Tailscale в nft: ts-forward, ts-input, ts-postrouting
таблицы nft: ip xgw, ip6 xgw6, ip nat, ip filter, ip6 nat, ip6 filter, ip mangle, ip6 mangle

== Гипотезы ==
К1: подтверждена — в цепочке output нет исключения для метки Tailscale 0x80000, правило meta mark set затирает её
К2: подтверждена — DNS к 100.100.100.100:53 перехватывается в Xray (исключения для tailscale0 нет); имя устройства через resolved: не разрешилось
К3: нет данных — шлюз сейчас не в режиме blocked (цепочки block_output нет); проявляется только в нём
К4: подтверждена — v6_guard отбивает IPv6 tailnet (fd7a:…) и IPv6-сокеты tailscaled: исключений нет
К5 (доп.): нет — адрес WAN не из 100.64.0.0/10
К6 (доп.): нет — tailscale0 не DNS по умолчанию
```
### nft.txt
```text
table ip xgw
  chain containers: правил 5
  chain prerouting: правил 9; type filter hook prerouting priority mangle; policy accept;
  chain output: правил 9; type route hook output priority mangle; policy accept;
  chain loopback_guard: правил 1; type filter hook output priority filter; policy accept;
  chain dns_direct: правил 1; type nat hook prerouting priority dstnat; policy accept;
  chain forward: правил 5; type filter hook forward priority filter; policy drop;
  chain postrouting: правил 1; type nat hook postrouting priority srcnat; policy accept;
table ip6 xgw6
  chain v6_guard: правил 7; type filter hook output priority filter; policy accept;
  chain forward: правил 2; type filter hook forward priority filter; policy accept;
table ip nat
  chain DOCKER: правил 0
  chain PREROUTING: правил 1; type nat hook prerouting priority dstnat; policy accept;
  chain OUTPUT: правил 1; type nat hook output priority dstnat; policy accept;
  chain POSTROUTING: правил 2; type nat hook postrouting priority srcnat; policy accept;
  chain ts-postrouting: правил 1
table ip filter
  chain DOCKER: правил 1
  chain DOCKER-FORWARD: правил 4
  chain DOCKER-BRIDGE: правил 1
  chain DOCKER-CT: правил 1
  chain DOCKER-INTERNAL: правил 0
  chain FORWARD: правил 3; type filter hook forward priority filter; policy accept;
  chain DOCKER-USER: правил 0
  chain ts-input: правил 5
  chain ts-forward: правил 4
  chain INPUT: правил 1; type filter hook input priority filter; policy accept;
table ip6 nat
  chain DOCKER: правил 0
  chain PREROUTING: правил 1; type nat hook prerouting priority dstnat; policy accept;
  chain OUTPUT: правил 1; type nat hook output priority dstnat; policy accept;
  chain ts-postrouting: правил 2
  chain POSTROUTING: правил 1; type nat hook postrouting priority srcnat; policy accept;
table ip6 filter
  chain DOCKER: правил 0
  chain DOCKER-FORWARD: правил 3
  chain DOCKER-BRIDGE: правил 0
  chain DOCKER-CT: правил 0
  chain DOCKER-INTERNAL: правил 0
  chain FORWARD: правил 3; type filter hook forward priority filter; policy accept;
  chain DOCKER-USER: правил 0
  chain ts-input: правил 3
  chain ts-forward: правил 3
  chain INPUT: правил 1; type filter hook input priority filter; policy accept;
table ip mangle
  chain PREROUTING: правил 1; type filter hook prerouting priority mangle; policy accept;
  chain OUTPUT: правил 1; type route hook output priority mangle; policy accept;
table ip6 mangle
  chain PREROUTING: правил 1; type filter hook prerouting priority mangle; policy accept;
  chain OUTPUT: правил 1; type route hook output priority mangle; policy accept;

--- ip xgw: chain output ---
type route hook output priority mangle; policy accept;
meta mark 0x00000002 return
ct direction reply return
meta l4proto != { tcp, udp } return
fib daddr type local return
ip daddr @reserved4 th dport != 53 return
udp sport 68 return
meta skuid 996 udp dport 123 return
meta skuid 996 tcp dport 4460 return
meta l4proto { tcp, udp } counter packets 201921 bytes 81031209 meta mark set 0x00000001

--- ip6 xgw6: chain v6_guard ---
type filter hook output priority filter; policy accept;
oifname "lo" accept
meta mark 0x00000002 accept
icmpv6 type { destination-unreachable, packet-too-big, time-exceeded, parameter-problem, nd-router-solicit, nd-router-advert, nd-neighbor-solicit, nd-neighbor-advert } accept
ip6 daddr { fe80::/10, ff00::/8 } accept
ct direction reply accept
meta l4proto tcp counter packets 7 bytes 588 reject with tcp reset
counter packets 17 bytes 2062 reject with icmpv6 admin-prohibited

--- ip nat: chain DOCKER ---


--- ip nat: chain PREROUTING ---
type nat hook prerouting priority dstnat; policy accept;
fib daddr type local counter packets 2018 bytes 137377 jump DOCKER

--- ip nat: chain OUTPUT ---
type nat hook output priority dstnat; policy accept;
ip daddr != 127.0.0.0/8 fib daddr type local counter packets 10 bytes 1930 jump DOCKER

--- ip nat: chain POSTROUTING ---
type nat hook postrouting priority srcnat; policy accept;
counter packets 328 bytes 23632 jump ts-postrouting
ip saddr 172.17.0.0/16 oifname != "docker0" counter packets 0 bytes 0 masquerade

--- ip nat: chain ts-postrouting ---
meta mark & 0x00ff0000 == 0x00040000 counter packets 0 bytes 0 masquerade

--- ip filter: chain DOCKER ---
iifname != "docker0" oifname "docker0" counter packets 0 bytes 0 drop

--- ip filter: chain DOCKER-FORWARD ---
counter packets 934 bytes 109064 jump DOCKER-CT
counter packets 934 bytes 109064 jump DOCKER-INTERNAL
counter packets 934 bytes 109064 jump DOCKER-BRIDGE
iifname "docker0" counter packets 0 bytes 0 accept

--- ip filter: chain DOCKER-BRIDGE ---
oifname "docker0" counter packets 0 bytes 0 jump DOCKER

--- ip filter: chain DOCKER-CT ---
oifname "docker0" ct state related,established counter packets 0 bytes 0 accept

--- ip filter: chain DOCKER-INTERNAL ---


--- ip filter: chain FORWARD ---
type filter hook forward priority filter; policy accept;
counter packets 0 bytes 0 jump ts-forward
counter packets 934 bytes 109064 jump DOCKER-USER
counter packets 934 bytes 109064 jump DOCKER-FORWARD

--- ip filter: chain DOCKER-USER ---


--- ip filter: chain ts-input ---
ip saddr 100.x.y.1 iifname "lo" counter packets 26 bytes 2012 accept
iifname "tailscale0" counter packets 0 bytes 0 accept
udp dport 41641 counter packets 77 bytes 4620 accept
ip saddr 100.x.y.7/23 iifname != "tailscale0" counter packets 0 bytes 0 return
ip saddr 100.64.0.0/10 iifname != "tailscale0" counter packets 31 bytes 2430 drop

--- ip filter: chain ts-forward ---
iifname "tailscale0" counter packets 0 bytes 0 meta mark set mark and 0xff00ffff xor 0x40000
meta mark & 0x00ff0000 == 0x00040000 counter packets 0 bytes 0 accept
ip saddr 100.64.0.0/10 oifname "tailscale0" counter packets 0 bytes 0 drop
oifname "tailscale0" counter packets 0 bytes 0 accept

--- ip filter: chain INPUT ---
type filter hook input priority filter; policy accept;
counter packets 17915 bytes 5078469 jump ts-input

--- ip6 nat: chain DOCKER ---


--- ip6 nat: chain PREROUTING ---
type nat hook prerouting priority dstnat; policy accept;
fib daddr type local counter packets 0 bytes 0 jump DOCKER

--- ip6 nat: chain OUTPUT ---
type nat hook output priority dstnat; policy accept;
ip6 daddr != ::1 fib daddr type local counter packets 0 bytes 0 jump DOCKER

--- ip6 nat: chain ts-postrouting ---
meta mark & 0x00ff0000 == 0x00040000 counter packets 0 bytes 0 # Warning: XT target MASQUERADE not found
xt target "MASQUERADE"

--- ip6 nat: chain POSTROUTING ---
type nat hook postrouting priority srcnat; policy accept;
counter packets 7 bytes 420 jump ts-postrouting

--- ip6 filter: chain DOCKER ---


--- ip6 filter: chain DOCKER-FORWARD ---
counter packets 0 bytes 0 jump DOCKER-CT
counter packets 0 bytes 0 jump DOCKER-INTERNAL
counter packets 0 bytes 0 jump DOCKER-BRIDGE

--- ip6 filter: chain DOCKER-BRIDGE ---


--- ip6 filter: chain DOCKER-CT ---


--- ip6 filter: chain DOCKER-INTERNAL ---


--- ip6 filter: chain FORWARD ---
type filter hook forward priority filter; policy accept;
counter packets 0 bytes 0 jump ts-forward
counter packets 0 bytes 0 jump DOCKER-USER
counter packets 0 bytes 0 jump DOCKER-FORWARD

--- ip6 filter: chain DOCKER-USER ---


--- ip6 filter: chain ts-input ---
ip6 saddr fd7a:…:1 iifname "lo" counter packets 17 bytes 2878 accept
iifname "tailscale0" counter packets 0 bytes 0 accept
udp dport 41641 counter packets 0 bytes 0 accept

--- ip6 filter: chain ts-forward ---
iifname "tailscale0" counter packets 0 bytes 0 meta mark set mark and 0xff00ffff xor 0x40000
meta mark & 0x00ff0000 == 0x00040000 counter packets 0 bytes 0 accept
oifname "tailscale0" counter packets 0 bytes 0 accept

--- ip6 filter: chain INPUT ---
type filter hook input priority filter; policy accept;
counter packets 24 bytes 3298 jump ts-input
```
### ip-rule.txt и ip-rule6.txt
```text
$ ip rule
0:	from all lookup local
95:	from all fwmark 0x3 lookup 101
100:	from all fwmark 0x1 lookup 100
5210:	from all fwmark 0x80000/0xff0000 lookup main
5230:	from all fwmark 0x80000/0xff0000 lookup default
5250:	from all fwmark 0x80000/0xff0000 unreachable
5270:	from all lookup 52
32766:	from all lookup main
32767:	from all lookup default
[код 0]
```
```text
$ ip -6 rule
0:	from all lookup local
5210:	from all fwmark 0x80000/0xff0000 lookup main
5230:	from all fwmark 0x80000/0xff0000 lookup default
5250:	from all fwmark 0x80000/0xff0000 unreachable
5270:	from all lookup 52
32766:	from all lookup main
[код 0]
```
### route52.txt и route52v6.txt
```text
$ ip route show table 52
100.x.y.2 dev tailscale0 
100.x.y.3 dev tailscale0 
100.x.y.4 dev tailscale0 
100.x.y.5 dev tailscale0 
100.100.100.100 dev tailscale0 
[код 0]
```
```text
$ ip -6 route show table 52
fd7a:…:2 dev tailscale0 metric 1024 pref medium
fd7a:115c:a1e0::/48 dev tailscale0 metric 1024 pref medium
[код 0]
```
### addr.txt
```text
$ ip -o addr
1: lo    inet 127.0.0.1/8 scope host lo\       valid_lft forever preferred_lft forever
1: lo    inet6 ::1/128 scope host noprefixroute \       valid_lft forever preferred_lft forever
2: enp3s0f0    inet 192.168.50.24/24 brd 192.168.50.255 scope global dynamic noprefixroute enp3s0f0\       valid_lft 72485sec preferred_lft 72485sec
3: enp4s0    inet 192.168.60.1/24 brd 192.168.60.255 scope global noprefixroute enp4s0\       valid_lft forever preferred_lft forever
4: xgwtun0    inet 169.254.10.1/32 scope global xgwtun0\       valid_lft forever preferred_lft forever
4: xgwtun0    inet6 fe80::cc71:cc6e:d84a:28d1/64 scope link stable-privacy \       valid_lft forever preferred_lft forever
5: docker0    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0\       valid_lft forever preferred_lft forever
6: tailscale0    inet 100.x.y.1/32 scope global tailscale0\       valid_lft forever preferred_lft forever
6: tailscale0    inet6 fd7a:…:1/128 scope global \       valid_lft forever preferred_lft forever
6: tailscale0    inet6 fe80::93cd:c342:281b:9c7b/64 scope link stable-privacy \       valid_lft forever preferred_lft forever
[код 0]
```
### resolved-ts0.txt
```text
$ resolvectl status tailscale0
Link 6 (tailscale0)
    Current Scopes: DNS
         Protocols: -DefaultRoute -LLMNR -mDNS -DNSOverTLS DNSSEC=no/unsupported
Current DNS Server: 100.100.100.100
       DNS Servers: 100.100.100.100 fd7a:…:2
        DNS Domain: tailnet-1 ~0.e.1.a.c.5.1.1.a.7.d.f.ip6.arpa
                    ~100.100.in-addr.arpa ~101.100.in-addr.arpa
                    ~102.100.in-addr.arpa ~103.100.in-addr.arpa
                    ~104.100.in-addr.arpa ~105.100.in-addr.arpa
                    ~106.100.in-addr.arpa ~107.100.in-addr.arpa
                    ~108.100.in-addr.arpa ~109.100.in-addr.arpa
                    ~110.100.in-addr.arpa ~111.100.in-addr.arpa
                    ~112.100.in-addr.arpa ~113.100.in-addr.arpa
                    ~114.100.in-addr.arpa ~115.100.in-addr.arpa
                    ~116.100.in-addr.arpa ~117.100.in-addr.arpa
                    ~118.100.in-addr.arpa ~119.100.in-addr.arpa
                    ~120.100.in-addr.arpa ~121.100.in-addr.arpa
                    ~122.100.in-addr.arpa ~123.100.in-addr.arpa
                    ~124.100.in-addr.arpa ~125.100.in-addr.arpa
                    ~126.100.in-addr.arpa ~127.100.in-addr.arpa
                    ~64.100.in-addr.arpa ~65.100.in-addr.arpa
                    ~66.100.in-addr.arpa ~67.100.in-addr.arpa
                    ~68.100.in-addr.arpa ~69.100.in-addr.arpa
                    ~70.100.in-addr.arpa ~71.100.in-addr.arpa
                    ~72.100.in-addr.arpa ~73.100.in-addr.arpa
                    ~74.100.in-addr.arpa ~75.100.in-addr.arpa
                    ~76.100.in-addr.arpa ~77.100.in-addr.arpa
                    ~78.100.in-addr.arpa ~79.100.in-addr.arpa
                    ~80.100.in-addr.arpa ~81.100.in-addr.arpa
                    ~82.100.in-addr.arpa ~83.100.in-addr.arpa
                    ~84.100.in-addr.arpa ~85.100.in-addr.arpa
                    ~86.100.in-addr.arpa ~87.100.in-addr.arpa
                    ~88.100.in-addr.arpa ~89.100.in-addr.arpa
                    ~90.100.in-addr.arpa ~91.100.in-addr.arpa
                    ~92.100.in-addr.arpa ~93.100.in-addr.arpa
                    ~94.100.in-addr.arpa ~95.100.in-addr.arpa
                    ~96.100.in-addr.arpa ~97.100.in-addr.arpa
                    ~98.100.in-addr.arpa ~99.100.in-addr.arpa ~домен-4
[код 0]
```
### ts-status.txt
```text
$ sudo -n tailscale status
100.x.y.1  устройство-1   пользователь@  linux    -                            
100.x.y.4   устройство-5   пользователь@  windows  offline, last seen 10d ago   
100.x.y.5   устройство-13  пользователь@  android  offline, last seen 10d ago   
100.x.y.6  устройство-4  пользователь@  android  offline, last seen 210d ago  
100.x.y.3   устройство-9   пользователь@  windows  -                            
100.x.y.2   устройство-7            пользователь@  linux    offline, last seen 8d ago    
[код 0]
```
### ts-prefs.txt
```text
$ sudo -n tailscale debug prefs
{
	"ControlURL": "https://controlplane.tailscale.com",
	"RouteAll": false,
	"ExitNodeID": "",
	"ExitNodeIP": "",
	"InternalExitNodePrior": "",
	"ExitNodeAllowLANAccess": false,
	"CorpDNS": true,
	"RunSSH": false,
	"RunWebClient": false,
	"WantRunning": true,
	"LoggedOut": false,
	"ShieldsUp": false,
	"AdvertiseTags": null,
	"Hostname": "",
	"NotepadURLs": false,
	"AdvertiseRoutes": null,
	"AdvertiseServices": null,
	"Sync": null,
	"NoSNAT": false,
	"NoStatefulFiltering": true,
	"NetfilterMode": 2,
	"AutoUpdate": {
		"Check": true,
		"Apply": true
	},
	"AppConnector": {
		"Advertise": false
	},
	"PostureChecking": false,
	"NetfilterKind": "",
	"RemoteConfig": false,
	"DriveShares": null,
	"Config": {
		"PrivateNodeKey": "privkey:0000000000000000000000000000000000000000000000000000000000000000",
		"OldPrivateNodeKey": "privkey:0000000000000000000000000000000000000000000000000000000000000000",
		"UserProfile": {
			"ID": 8318053163072880,
			"LoginName": "почта@…",
			"DisplayName": "пользователь-2",
			"ProfilePicURL": "https://домен-8/…"
		},
		"NetworkLockKey": "nlpriv:00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
		"NodeID": "nf6BHgrVy411CNTRL"
	}
}
[код 0]
```
### ts-netcheck.txt
```text
$ sudo -n tailscale netcheck
2026/10/20 13:12:49 portmap: monitor: gateway and self IP changed: gw=192.168.50.1 self=192.168.50.24
2026/10/20 13:12:49 portmap: [v1] Got PMP response; IP: 10.68.122.29, epoch: 661931
2026/10/20 13:12:49 portmap: [v1] Got PCP response: epoch: 661931
2026/10/20 13:12:49 portmap: [v1] UPnP reply {Location:http://192.168.50.1:33755/… Server:AsusWRT/102 UPnP/1.1 MiniUPnPd/2.2.0 USN:uuid:[UUID-скрыт]::urn:schemas-upnp-org:device:InternetGatewayDevice:1}, "HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=120\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\nUSN: uuid:[UUID-скрыт]::urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\nEXT:\r\nSERVER: AsusWRT/102 UPnP/1.1 MiniUPnPd/2.2.0\r\nLOCATION: http://192.168.50.1:33755/… \"http://домен-5/…"; ns=01\r\n01-NLS: 1704067249\r\домен-6: 1704067249\r\домен-7: 1337\r\n\r\n"
2026/10/20 13:12:49 portmap: [v1] UPnP reply {Location:http://192.168.50.1:33755/… Server:AsusWRT/102 UPnP/1.1 MiniUPnPd/2.2.0 USN:uuid:[UUID-скрыт]::urn:schemas-upnp-org:device:InternetGatewayDevice:1}, "HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=120\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\nUSN: uuid:[UUID-скрыт]::urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\nEXT:\r\nSERVER: AsusWRT/102 UPnP/1.1 MiniUPnPd/2.2.0\r\nLOCATION: http://192.168.50.1:33755/… \"http://домен-5/…"; ns=01\r\n01-NLS: 1704067249\r\домен-6: 1704067249\r\домен-7: 1337\r\n\r\n"
2026/10/20 13:12:49 portmap: [v1] UPnP reply {Location:http://192.168.50.1:33755/… Server:AsusWRT/102 UPnP/1.1 MiniUPnPd/2.2.0 USN:uuid:[UUID-скрыт]::urn:schemas-upnp-org:device:InternetGatewayDevice:1}, "HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=120\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\nUSN: uuid:[UUID-скрыт]::urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\nEXT:\r\nSERVER: AsusWRT/102 UPnP/1.1 MiniUPnPd/2.2.0\r\nLOCATION: http://192.168.50.1:33755/… \"http://домен-5/…"; ns=01\r\n01-NLS: 1704067249\r\домен-6: 1704067249\r\домен-7: 1337\r\n\r\n"
2026/10/20 13:12:49 portmap: UPnP meta changed: [{Location:http://192.168.50.1:33755/… Server:AsusWRT/102 UPnP/1.1 MiniUPnPd/2.2.0 USN:uuid:[UUID-скрыт]::urn:schemas-upnp-org:device:InternetGatewayDevice:1}]

Report:
	* Time: 2026-10-20 13:12:51.102254288+03:00
	* UDP: true
	* IPv4: yes, внешний-IP-1:50789
	* IPv6: no, but OS has support
	* MappingVariesByDestIP: false
	* PortMapping: UPnP, NAT-PMP, PCP
	* CaptivePortal: false
	* Nearest DERP: Frankfurt
	* DERP latency:
		- fra: 88.6ms  (Frankfurt)
		- ams: 88.9ms  (Amsterdam)
		- nue: 92.9ms  (Nuremberg)
		- par: 138.7ms (Paris)
		- mad: 143.3ms (Madrid)
		- lhr: 145ms   (London)
		- nyc: 151.4ms (New York City)
		- waw: 166ms   (Warsaw)
		- tor: 167.2ms (Toronto)
		- hel: 174.8ms (Helsinki)
		- mia: 178.2ms (Miami)
		- den: 189.6ms (Denver)
		- dfw: 191.7ms (Dallas)
		- dbi: 200.1ms (Dubai)
		- iad: 213.5ms (Ashburn)
		- sfo: 215.7ms (San Francisco)
		- nai: 222.3ms (Nairobi)
		- ord: 223.9ms (Chicago)
		- blr: 227.1ms (Bengaluru)
		- lax: 251.1ms (Los Angeles)
		- sin: 264.2ms (Singapore)
		- hnl: 267.9ms (Honolulu)
		- sea: 279.8ms (Seattle)
		- jnb: 287.2ms (Johannesburg)
		- hkg: 304.1ms (Hong Kong)
		- tok: 326.2ms (Tokyo)
		- sao: 366.9ms (São Paulo)
		- syd: 452.2ms (Sydney)
[код 0]
```
### ts-journal.txt
```text
строк за сутки: 168
совпадений: magicsock 9, derp 8, health 8, netcheck 1, error 15, timeout 0, udp 3, endpoint 1, NeedsLogin 4, netfilter 1, dns 16

--- последние 200 строк ---
2026-10-20T13:09:00+03:00 устройство-1 systemd[1]: Starting tailscaled.service - Tailscale node agent...
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 261: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 262: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 263: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 264: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 265: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 258: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 266: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 267: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 268: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: GetCapability 256: unrecognized error code (0xa)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: TPM: successfully read all properties
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Program starting: v1.104.1-t7f4efe814-g8da26756c, Go 1.27.1: []string{"/usr/sbin/tailscaled", "--state=/var/lib/tailscale/tailscaled.state", "--socket=/run/tailscale/tailscaled.sock", "--port=41641"}
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: LogID: c2ac3d31391fdf2870793c7d0c155b74247b9bcea25c960d405112254f9a31dc
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: logpolicy: using $STATE_DIRECTORY, "/var/lib/tailscale"
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: домен-13 /var/lib/tailscale/tailscaled.log.conf: open /var/lib/tailscale/tailscaled.log.conf: no such file or directory
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: домен-14 for /var/lib/tailscale/tailscaled.log.conf: config is nil
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: dns: [resolved-ping=yes rc=resolved resolved=file nm=yes nm-resolved=yes nm-safe=no resolv-conf-mode=stub ret=systemd-resolved]
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: dns: using "systemd-resolved" mode
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: creating dns cleanup: route ip+net: no such network interface
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: router: enumerating tailscale0 addresses for cleanup failed: failed to look up link "tailscale0": Link not found
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: домен-15(tun "tailscale0") ...
2026-10-20T13:09:00+03:00 устройство-1 systemd[1]: Started tailscaled.service - Tailscale node agent.
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: dns: [resolved-ping=yes rc=resolved resolved=file nm=yes nm-resolved=yes nm-safe=no resolv-conf-mode=stub ret=systemd-resolved]
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: dns: using "systemd-resolved" mode
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: dns: using *домен-16
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: link state: домен-17{defaultRoute=enp3s0f0 ifs={docker0:[172.17.0.1/16] enp3s0f0:[192.168.50.24/24] enp4s0:[192.168.60.1/24]} v4=true v6=false}
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: magicsock: disco key = d:f46d02b7800fe4c7
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Creating WireGuard device...
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Bringing WireGuard device up...
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Bringing router up...
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: router: using firewall mode pref
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: router: portUpdate(port=41641, network=udp6)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: external route: up
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: router: default choosing iptables
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: router: netfilter running in iptables mode v6 = true, v6filter = true, v6nat = true
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Clearing router settings...
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: router: portUpdate(port=41641, network=udp4)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Starting network monitor...
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Engine created.
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: monitor: gateway and self IP changed: gw=192.168.50.1 self=192.168.50.24
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: pm: migrating "_daemon" profile to new format
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: envknob: PORT="41641"
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: logpolicy: using $STATE_DIRECTORY, "/var/lib/tailscale"
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: linkChange: in state NoState; PAC or proxyConfig changed; updating routes
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: got LocalBackend in 84ms
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Start
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: ipnext: active extensions: captiveportal, acme, portlist, posture, clientupdate, conn25, connreject, favorites, relayserver, routecheck, serviceclientprefs, taildrop
2026-10-20T13:09:00+03:00 устройство-1 systemd[1]: tailscaled.service: Got notification message from PID 27650, but reception only permitted for main PID 27608
2026-10-20T13:09:00+03:00 устройство-1 systemd[1]: tailscaled.service: Got notification message from PID 27650, but reception only permitted for main PID 27608
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: profile data directory: profile not found
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Backend: logs: be:c2ac3d31391fdf2870793c7d0c155b74247b9bcea25c960d405112254f9a31dc fe:
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: Switching ipn state NoState -> NeedsLogin (WantRunning=false, nm=false)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: blockEngineUpdates(true)
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: wgengine: Reconfig: configuring router
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: wgengine: Reconfig: user dialer
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: wgengine: Reconfig: configuring DNS
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: dns: Set: {DefaultResolvers:[] Routes:{} SearchDomains:[] Hosts:0}
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: dns: Resolvercfg: {Routes:{} Hosts:0 LocalDomains:[]}
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: dns: OScfg: {}
2026-10-20T13:09:00+03:00 устройство-1 tailscaled[ключ]: health(warnable=wantrunning-false): error: Tailscale is stopped.
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: localapi: [POST] /localapi/v0/check-prefs
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: localapi: [POST] /localapi/v0/start
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: control: домен-18 ...
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: control: mapRoutine: exiting
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: control: authRoutine: exiting
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: control: updateRoutine: exiting
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: control: домен-18 done.
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: Start
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: Start: updated prefs: Prefs{ra=false dns=true want=true routes=[] statefulFiltering=false nf=on update=check Persist=nil}, reason: [домен-19]
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: generating new machine key
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: machine key written to store
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: profile data directory: profile not found
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: Backend: logs: be:c2ac3d31391fdf2870793c7d0c155b74247b9bcea25c960d405112254f9a31dc fe:
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: health(warnable=warming-up): error: Tailscale is starting. Please wait.
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: Switching ipn state NoState -> NeedsLogin (WantRunning=true, nm=false)
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: blockEngineUpdates(true)
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: Reconfig(down): no changes made to Engine config
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: health(warnable=wantrunning-false): ok
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: localapi: [POST] /localapi/v0/login-interactive
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: StartLoginInteractiveAs("root"): url=false
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: control: домен-20(2)
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: control: LoginInteractive -> regen=true
2026-10-20T13:09:19+03:00 устройство-1 tailscaled[ключ]: control: doLogin(regen=true, hasUrl=false)
2026-10-20T13:09:20+03:00 устройство-1 tailscaled[ключ]: control: control server key from https://controlplane.tailscale.com: ts2021=[ключ], legacy=[ключ]
2026-10-20T13:09:20+03:00 устройство-1 tailscaled[ключ]: control: Generating a new nodekey.
2026-10-20T13:09:20+03:00 устройство-1 tailscaled[ключ]: control: RegisterReq: onode= node=[ключ] fup=false nks=false
2026-10-20T13:09:23+03:00 устройство-1 tailscaled[ключ]: control: RegisterReq: got response; nodeKeyExpired=false, machineAuthorized=false; authURL=true
2026-10-20T13:09:23+03:00 устройство-1 tailscaled[ключ]: control: AuthURL is https://login.tailscale.com/…
2026-10-20T13:09:23+03:00 устройство-1 tailscaled[ключ]: control: doLogin(regen=false, hasUrl=true)
2026-10-20T13:09:23+03:00 устройство-1 tailscaled[ключ]: Received auth URL: https://домен-21...
2026-10-20T13:09:23+03:00 устройство-1 tailscaled[ключ]: popBrowserAuthNow("root"): url=true, key-expired=false
2026-10-20T13:09:23+03:00 устройство-1 tailscaled[ключ]: control: RegisterReq: onode= node=[ключ] fup=true nks=false
2026-10-20T13:09:24+03:00 устройство-1 tailscaled[ключ]: health(warnable=warming-up): ok
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: localapi: [POST] /localapi/v0/check-prefs
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: localapi: [POST] /localapi/v0/start
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: control: домен-18 ...
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: control: updateRoutine: exiting
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: control: mapRoutine: exiting
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: health(warnable=login-state): error: You are logged out.
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: control: authRoutine: exiting
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: control: домен-18 done.
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: Start
2026-10-20T13:09:49+03:00 устройство-1 systemd[1]: tailscaled.service: Got notification message from PID 27792, but reception only permitted for main PID 27608
2026-10-20T13:09:49+03:00 устройство-1 systemd[1]: tailscaled.service: Got notification message from PID 27792, but reception only permitted for main PID 27608
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: Start: updated prefs: Prefs{ra=false dns=true want=true routes=[] statefulFiltering=false nf=on update=check Persist=nil}, reason: [домен-19]
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: profile data directory: profile not found
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: Backend: logs: be:c2ac3d31391fdf2870793c7d0c155b74247b9bcea25c960d405112254f9a31dc fe:
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: health(warnable=login-state): ok
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: Switching ipn state NoState -> NeedsLogin (WantRunning=true, nm=false)
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: blockEngineUpdates(true)
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: Reconfig(down): no changes made to Engine config
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: localapi: [POST] /localapi/v0/login-interactive
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: StartLoginInteractiveAs("root"): url=false
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: control: домен-20(2)
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: control: LoginInteractive -> regen=true
2026-10-20T13:09:49+03:00 устройство-1 tailscaled[ключ]: control: doLogin(regen=true, hasUrl=false)
2026-10-20T13:09:50+03:00 устройство-1 tailscaled[ключ]: control: control server key from https://controlplane.tailscale.com: ts2021=[ключ], legacy=[ключ]
2026-10-20T13:09:50+03:00 устройство-1 tailscaled[ключ]: control: Generating a new nodekey.
2026-10-20T13:09:50+03:00 устройство-1 tailscaled[ключ]: control: RegisterReq: onode= node=[ключ] fup=false nks=false
2026-10-20T13:09:50+03:00 устройство-1 tailscaled[ключ]: control: controlhttp: forcing port 443 dial due to recent noise dial
2026-10-20T13:09:53+03:00 устройство-1 tailscaled[ключ]: control: RegisterReq: got response; nodeKeyExpired=false, machineAuthorized=false; authURL=true
2026-10-20T13:09:53+03:00 устройство-1 tailscaled[ключ]: control: AuthURL is https://login.tailscale.com/…
2026-10-20T13:09:53+03:00 устройство-1 tailscaled[ключ]: control: doLogin(regen=false, hasUrl=true)
2026-10-20T13:09:53+03:00 устройство-1 tailscaled[ключ]: control: RegisterReq: onode= node=[ключ] fup=true nks=false
2026-10-20T13:09:53+03:00 устройство-1 tailscaled[ключ]: Received auth URL: https://домен-21...
2026-10-20T13:09:53+03:00 устройство-1 tailscaled[ключ]: popBrowserAuthNow("root"): url=true, key-expired=false
2026-10-20T13:12:05+03:00 устройство-1 tailscaled[ключ]: health(warnable=login-state): error: You are logged out. The last login error was: register request: http 410: auth path not found
2026-10-20T13:12:05+03:00 устройство-1 tailscaled[ключ]: Received error: register request: http 410: auth path not found
2026-10-20T13:12:05+03:00 устройство-1 tailscaled[ключ]: control: doLogin(regen=false, hasUrl=true)
2026-10-20T13:12:05+03:00 устройство-1 tailscaled[ключ]: control: RegisterReq: onode= node=[ключ] fup=true nks=false
2026-10-20T13:12:05+03:00 устройство-1 tailscaled[ключ]: control: RegisterReq: got response; nodeKeyExpired=false, machineAuthorized=true; authURL=false
2026-10-20T13:12:05+03:00 устройство-1 tailscaled[ключ]: blockEngineUpdates(false)
2026-10-20T13:12:05+03:00 устройство-1 tailscaled[ключ]: health(warnable=login-state): ok
2026-10-20T13:12:06+03:00 устройство-1 systemd[1]: tailscaled.service: Got notification message from PID 28630, but reception only permitted for main PID 27608
2026-10-20T13:12:06+03:00 устройство-1 systemd[1]: tailscaled.service: Got notification message from PID 28630, but reception only permitted for main PID 27608
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: control: netmap: got new dial plan from control
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: using tailnet default auto-update setting: true
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: EditPrefs: MaskedPrefs{AutoUpdate={Apply=true}}
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: offline auto-update: starting update checks
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: magicsock: new contact: control-netmap usec=185504171 cached=false
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: active login: почта@…
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: netmap: suggested exit node: no preferred DERP, try again later
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: offline auto-update: stopping update checks
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: Switching ipn state NeedsLogin -> Starting (WantRunning=true, nm=true)
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: magicsock: SetPrivateKey called (init)
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: wgengine: Reconfig: configuring router
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: portmapper: UPnP meta changed: [{Location:http://192.168.50.1:33755/… Server:AsusWRT/102 UPnP/1.1 MiniUPnPd/2.2.0 USN:uuid:[UUID-скрыт]::urn:schemas-upnp-org:device:InternetGatewayDevice:1}]
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: router: enabling connmark-based rp_filter workaround
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: wgengine: Reconfig: user dialer
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: tsdial: bart table size: 7
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: wgengine: Reconfig: configuring DNS
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: dns: Set: {DefaultResolvers:[] Routes:{tailnet-1.:[] домен-4.:[внешний-IP-87 внешний-IPv6-86]}+65arpa SearchDomains:[tailnet-1.] Hosts:0}
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: dns: Resolvercfg: {Routes:{домен-4.:[внешний-IP-87 внешний-IPv6-86]} Hosts:0 LocalDomains:[tailnet-1.]+65arpa}
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: dns: OScfg: {Nameservers:[100.100.100.100 fd7a:…:2] SearchDomains:[tailnet-1.] MatchDomains:[tailnet-1. домен-4.]+65arpa}
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: peerapi: serving on http://100.x.y.1:33406
2026-10-20T13:12:06+03:00 устройство-1 tailscaled[ключ]: peerapi: serving on http://[fd7a:…:1]:41473
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: netcheck: DetectCaptivePortal(found=false)
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: magicsock: home DERP changing from derp-0 [0ms] to derp-18 [75ms] (forced=false)
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: magicsock: home is now derp-18 (par)
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: magicsock: adding connection to derp-18 for home-keep-alive
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: magicsock: 1 active derp conns: derp-18=cr0s,wr0s
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: updating netmap in disk cache
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: домен-22: connecting to derp-18 (par)
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: magicsock: endpoints changed: 10.68.122.29:41641 (portmap), внешний-IP-1:46499 (stun), 172.17.0.1:41641 (local), 192.168.50.24:41641 (local), 192.168.60.1:41641 (local)
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: control: NetInfo: NetInfo{varies=false ipv6=false ipv6os=true udp=true icmpv4=false derp=#18 portmap=active-UMC link="" firewallmode="ipt-default"}
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: Switching ipn state Starting -> Running (WantRunning=true, nm=true)
2026-10-20T13:12:08+03:00 устройство-1 tailscaled[ключ]: magicsock: derp-18 connected; connGen=1
```
### xgw-status.txt
```text
$ sudo -n xgw status
Состояние: HEALTHY с 20.10 11:53 — вмешательство не требуется
Xray 26.10.10: отвечает
sing-box 1.14.3: работает, серверов через него: 30
Перехват: включён — сеть enp4s0, эта машина и контейнеры Docker
Основной сервер: proxy-ae-1cbc «🇦🇪 x10📶🛜 ОАЭ | Дубай | AI» — 24 Мбит/с, с 20.10 11:56; весь трафик через него, другие участники наготове
Узлов: 4 активных, 70 запасных (отброшено 5 недоступных/служебных, схлопнуто 21 дублей); из отброшенных 3 — домен не разрешается; отключено или убрано в панели: 19
Участники балансировщика (4), уровень приоритета «высокий»:
  proxy-es-763b        жив, 692 мс, 3,3 Мбит/с        🇪🇸 x10 🛜 Испания | AI [высокий] [x10] [xray]
  proxy-tr-76a6        жив, 588 мс, 21 Мбит/с          🇹🇷 x10 🛜 | Турция | AI [высокий] [x10] [xray]
  proxy-ae-1cbc        жив, 255 мс, 24 Мбит/с         🇦🇪 x10📶🛜 ОАЭ | Дубай | AI [высокий] [x10] [xray+frag]  ← основной
  proxy-pl-0377        жив, 385 мс, 24 Мбит/с         🇵🇱 x10🛜 Польша 2 | AI | NO TORRENT [высокий] [x10] [xray]
Запасные (70):
  spare-eu-0498        CONNECT_FAIL, 0 Б за 2.97 с (19.10 22:17) 🇪🇺 x10 🛜 Европа  🚀🚀 АВТО [x10] [xray]
  spare-tr-0957        OK, 57620 Б за 0.52 с (20.10 12:24)      🇹🇷💳Турция Torrent [sb+frag]
  spare-jp-0dec        OK, 57620 Б за 1.37 с (20.10 12:24)      🇯🇵 Япония X [xray]  ← резервный выход
  spare-lv-12ef        OK, 302 Б за 0.2 с (19.10 22:17)         🇱🇻 x1 🛜 Латвия | AI [x1] [xray]
  spare-ch-152d        CONNECT_FAIL, 0 Б за 2.2 с (20.10 12:24) 🇨🇭⚡Швейцария-1 [xray]
  spare-ro-1881        OK, 296 Б за 0.43 с (19.10 22:18)        🇷🇴 x10 🛜 | Румыния | Hysteria🚀🚀 [x10] [sb]
  spare-it-1a7e        OK, 57620 Б за 0.3 с (20.10 12:24)       🇮🇹Италия Torrent [sb+frag]
  spare-ru-2b35        OK, 57620 Б за 0.28 с (20.10 12:24)      🇷🇺 1. РФ→ 🇸🇪 Швеция | Все [xray]
  spare-us-2def        OK, 301 Б за 0.54 с (19.10 22:17)        🇺🇸 | x1 📶🛜 США ✈️ [x1] [xray]
  spare-lv-2f4a        OK, 302 Б за 0.38 с (19.10 22:17)        🇱🇻 ㊙️ x1 | Анонимайзер-1 | Латвия [x1] [xray]
  spare-eu-3114        OK, 57620 Б за 0.39 с (20.10 12:24)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-nl-321f        OK, 57620 Б за 0.56 с (20.10 12:24)      🇳🇱 Нидерланды X [xray]
  spare-jp-35e4        OK, 57620 Б за 2.17 с (20.10 12:24)      🇯🇵 Япония G [xray+frag]
  spare-eu-3698        OK, 57620 Б за 0.34 с (20.10 12:25)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb+frag]
  spare-eu-3810        CONNECT_FAIL, 0 Б за 5.01 с (20.10 12:25) 🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-gb-3ab8        OK, 57620 Б за 0.32 с (20.10 12:25)      🇬🇧Англия SS [sb]
  spare-md-3ae5        OK, 57620 Б за 0.32 с (20.10 12:25)      🇲🇩Молдова [sb]
  spare-jp-3fb4        OK, 57620 Б за 0.4 с (20.10 12:25)       🇯🇵Япония [sb]
  spare-eu-4228        OK, 305 Б за 0.43 с (19.10 22:17)        🇪🇺 x1 📶🛜 Европа АВТО [x1] [xray]
  spare-de-4531        OK, 57620 Б за 0.33 с (20.10 12:25)      🇩🇪 Германия [xray]
  spare-ca-473c        SLOW, 57620 Б за 8.43 с (20.10 12:25)    🇨🇦Канада SS [sb]
  spare-il-4b86        OK, 300 Б за 2.68 с (19.10 22:17)        🇮🇱 x1 🛜 Израиль | AI [x1] [xray]
  spare-hk-5119        OK, 57620 Б за 0.41 с (20.10 12:25)      🇭🇰Гонконг [sb]
  spare-us-530b        TIMEOUT, 0 Б за 15.05 с (19.10 22:19)    🇺🇸 ㊙️x10 | Анонимайзер-5 | США  [x10] [xray]
  spare-kz-544f        OK, 57620 Б за 0.36 с (20.10 12:25)      🇰🇿💳Казахстан [sb]
  spare-br-60f3        OK, 57620 Б за 0.35 с (20.10 12:25)      🇧🇷💳Бразилия [sb]
  spare-by-6400        OK, 299 Б за 0.73 с (19.10 22:18)        🇧🇾 ㊙️ x1 | Анонимайзер-3 | Беларусь [x1] [xray]
  spare-fi-66f4        CONNECT_FAIL, 0 Б за 7.01 с (20.10 12:25) 🇫🇮 Финляндия G [xray]
  spare-tr-672f        OK, 57620 Б за 1.05 с (20.10 12:26)      🇹🇷 Турция [sb]
  spare-eu-6894        CONNECT_FAIL, 0 Б за 2.19 с (20.10 12:26) 🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [xray]
  spare-eu-6df8        OK, 57620 Б за 0.36 с (20.10 12:26)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-pl-736d        OK, 57620 Б за 0.42 с (20.10 12:26)      🇵🇱 Польша [xray]
  spare-ch-7706        CONNECT_FAIL, 0 Б за 5.01 с (20.10 12:26) 🇨🇭🎮Швейцария GAMING [xray]
  spare-fi-77cb        TIMEOUT, 0 Б за 15.05 с (20.10 12:26)    🇫🇮 Финляндия [xray]
  spare-pl-7e92        OK, 305 Б за 0.44 с (19.10 22:17)        🇵🇱 x1🛜 Польша | AI [x1] [xray]
  spare-fi-7fd2        TIMEOUT, 0 Б за 15.06 с (20.10 12:27)    🇫🇮🎮Финляндия GAMING [xray+frag]
  spare-nl-88d6        OK, 306 Б за 0.2 с (19.10 22:19)         🇳🇱  x10📶🛜 Нидерланды  🚀 🚀 | AI [x10] [xray]
  spare-nl-8e27        OK, 57620 Б за 2.41 с (20.10 12:27)      🇳🇱 Нидерланды2 [xray]
  spare-eu-a65c        OK, 57620 Б за 0.34 с (20.10 12:27)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-ai-a88d        CONNECT_FAIL, 0 Б за 3.44 с (19.10 22:18) x1 🛜 Германия 3 🚀🚀 | AI [x1] [xray]
  spare-tr-aa10        OK, 302 Б за 0.46 с (19.10 22:19)        🇹🇷 ㊙️ x10 | Анонимайзер-2 | Турция [x10] [xray]
  spare-nl-abe2        OK, 57620 Б за 0.41 с (20.10 12:27)      🇳🇱 Нидерланды G [xray]
  spare-eu-aefc        OK, 57620 Б за 0.29 с (20.10 12:27)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-sg-b017        OK, 304 Б за 0.74 с (19.10 22:17)        🇸🇬 x1 🛜 Сингапур 2 [x1] [xray]
  spare-eu-b1d7        OK, 57620 Б за 0.32 с (20.10 12:27)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-in-b726        OK, 57620 Б за 0.38 с (20.10 12:28)      🇮🇳💳Индия [sb]
  spare-ru-bab9        OK, 57620 Б за 0.29 с (20.10 12:28)      🇷🇺 1. РФ→ 🇸🇪 Швеция 🚫 iphone [xray]
  spare-it-bb18        OK, 57620 Б за 0.28 с (20.10 12:28)      🇮🇹Италия SS [sb]
  spare-by-bb59        OK, 304 Б за 0.7 с (19.10 22:17)         🇧🇾 ㊙️ x1 | Анон-3 | Беларусь | HY2 [x1] [sb]
  spare-gb-c027        CONNECT_FAIL, 0 Б за 1.08 с (20.10 12:28) 🇬🇧 Великобритания [sb]
  spare-de-c1c7        OK, 57620 Б за 0.33 с (20.10 12:28)      🇩🇪 Германия G [xray]
  spare-eu-c3a3        OK, 57620 Б за 0.39 с (20.10 12:29)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb+frag]
  spare-ru-c4e3        OK, 57620 Б за 0.23 с (20.10 12:29)      🇷🇺 Россия [xray]
  spare-ca-ce1c        OK, 57620 Б за 0.8 с (20.10 12:29)       🇨🇦Канада Torrent [sb]
  spare-us-ce38        OK, 57620 Б за 1.09 с (20.10 12:29)      🇺🇸США Torrent [sb]
  spare-jp-d2a0        OK, 298 Б за 1.03 с (19.10 22:18)        🇯🇵 x1 🛜 Япония + [x1] [xray]
  spare-ru-d309        OK, 57620 Б за 0.21 с (20.10 12:29)      🇷🇺💳Россия [xray+frag]
  spare-ee-d34a        OK, 57620 Б за 0.23 с (20.10 12:29)      🇪🇪 Эстония [sb]
  spare-nl-d3c8        OK, 305 Б за 0.32 с (19.10 22:19)        🇳🇱  x10📶🛜 Нидерланды 2  🚀 🚀 | AI [x10] [xray]
  spare-eu-d428        OK, 57620 Б за 0.26 с (20.10 12:29)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-ca-d546        TIMEOUT, 0 Б за 15.05 с (19.10 22:18)    🇨🇦 x1 🛜 Канада | AI ✈️ [x1] [xray]
  spare-nl-ded3        SLOW, 306 Б за 14.8 с (19.10 22:19)      🇳🇱 x10📶🛜 Нидерланды  3 🚀 🚀 | AI [x10] [xray]
  spare-pl-e142        OK, 299 Б за 0.35 с (19.10 22:19)        🇵🇱 x10🛜 Польша 3 | HY2 | NO TORRENT [x10] [sb]
  spare-us-e475        OK, 300 Б за 0.62 с (19.10 22:18)        🇺🇸 x1 📶🛜 США АВТО | AI [x1] [xray]
  spare-de-eb16        OK, 300 Б за 0.54 с (19.10 22:18)        🇩🇪 x1 Германия | AI | NO TORRENT [x1] [xray]
  spare-eu-f0be        OK, 57620 Б за 0.32 с (20.10 12:29)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-de-f327        OK, 303 Б за 0.28 с (19.10 22:19)        🇩🇪 x10 🛜 Германия 2 🚀🚀 | AI [x10] [xray]
  spare-nl-f4a0        TIMEOUT, 0 Б за 15.05 с (20.10 12:31)    🇳🇱🎮Нидерланды GAMING [xray+frag]
  spare-eu-fd8e        OK, 57620 Б за 0.44 с (20.10 12:31)      🇪🇺 🚀Авто | Лучший сервер ⚡⚡ *** [sb]
  spare-ro-fddc        OK, 298 Б за 1.07 с (19.10 22:18)        🇷🇴 x1📶🛜 Румыния, Молдова АВТО [x1] [xray]
Резервный выход: spare-jp-0dec «🇯🇵 Япония X» (безлимит) — через него идёт трафик, только когда все участники не отвечают; ядро его не пробует
Квота «conn-liberty»: израсходовано 0.0 ГБ, лимита нет — безлимитная, действует до 07.11 03:00
Квота «libhub»: израсходовано 2835.3 ГБ из 5905.6 ГБ, осталось 3070.2 ГБ, действует до 22.11 17:00
Квота «домен-12»: израсходовано 39.9 ГБ, лимита нет — безлимитная, действует до 09.11 12:31
Трафик проверок: ~728 МБ/сут (пробы 664, сканы 64; лимит 1024); сквозная проверка ещё ~249 МБ/сут, замер скорости — до ~16 МБ/сут
  всего ~992 МБ/сут, ~29.8 ГБ/мес: проба 57 620 Б (измерено); участников — 4, проба раз в 30 с; запасных — 46, скан раз в 60 мин
  за месяц это ~5 % квоты подписки «libhub» (~9287 МБ квоты в сутки с множителями)
Последние события:
  20.10 12:31  apply: профиль обхода (spare-nl-f4a0): применено через API без перезапуска: rmo+ado: spare-nl-f4a0
  20.10 12:31  fragment: «🇳🇱🎮Нидерланды GAMING» без дробления ClientHello не отвечает — оно включено снова
  20.10 12:30  apply: обновление подписки: применено через API без перезапуска: rmo+ado: spare-ch-152d; rmo+ado: spare-eu-6894
  20.10 12:30  singbox: конфиг sing-box перечитан: мостов 115
  20.10 12:29  apply: профиль обхода (spare-nl-f4a0): применено через API без перезапуска: rmo+ado: spare-nl-f4a0
  20.10 12:29  profile: «🇪🇺 🚀Авто | Лучший сервер ⚡⚡ ***» отвечает на профиле «sing-box с дроблением TLS» — он закреплён (был «sing-box»)
  20.10 12:28  apply: профиль обхода (spare-eu-c3a3): применено через API без перезапуска: rmo+ado: spare-eu-c3a3
  20.10 12:28  profile: «🇪🇺 🚀Авто | Лучший сервер ⚡⚡ ***» не отвечает на профиле «Xray» — пробую «sing-box с дроблением TLS»
[код 0]
```
### xgw-diag.txt
```text
$ sudo -n xgw diag
WARN  Система: Ubuntu 24.04.5 LTS, Python 3.12 — XGW проверялся только на Ubuntu 26.04
OK    Конфиг: /etc/xgw/config.toml читается; режим — сеть enp4s0 и эта машина
OK    Программы: nft, ip, systemctl, nmcli, dnsmasq на месте
OK    Xray: версия 26.10.10, GET-проверка (httpMethod) поддерживается
OK    Ядро: ядро принимает правила TPROXY (tproxy, fib, ct, masquerade)
OK    TUN: /dev/net/tun есть; интерфейс xgwtun0 — для контейнеров Docker
OK    Файрвол: ufw и Docker перехвату не мешают; контейнеры Docker — через VPN
OK    LAN: enp4s0: профиль xgw-lan активен
OK    Подсеть LAN: 192.168.60.0/24 не пересекается с другими сетями машины
OK    Порты: служебные порты заняты работающим Xray
OK    Xray API: API и метрики отвечают; живых участников 4 из 4
OK    sing-box: версия 1.14.3
OK    sing-box: конфиг: принят sing-box check, мостов: 115
OK    Время: часы синхронизированы; служба времени — systemd-timesync
OK    Сон: цели сна замаскированы
OK    IPv6: глобальный IPv6-адрес на tailscale0: наружу IPv6 машины не выпускает фаервол (v6_guard)
OK    Службы: xgw-net, xgw-xray, xgw-singbox, xgw, xgw-dhcp работают
OK    Перехват: включён, правила загружены
OK    Журнал: предупреждения демона — с уровнем warning (journalctl -u xgw -p warning)
OK    Панель: войти заново — правая кнопка по ярлыку «XGW», «Войти заново»
OK    Трафик проверок: ~728 МБ в сутки при 4 участниках и 70 запасных (лимит 1024 МБ); вместе со сквозной проверкой и замером скорости — ~992 МБ в сутки, ~30 ГБ в месяц (проба 57620 Б, измерено); за месяц это ~5 % квоты подписки «libhub» (с множителями серверов)
OK    домен-11: напрямую: 57620 Б за 0.4 с
OK    домен-11: через Xray: 57620 Б за 0.3 с
OK    bootstrap DNS: отвечают все 3
Итог: OK — 23, WARN — 1, FAIL — 0
[код 0]
```

## Наблюдения
- Перед снимком заказчик поручил установить Tailscale: на шлюзе его не было (нет бинарника,
  пакета, юнита tailscaled, интерфейса tailscale0). Установлен 1.104.1 с официального
  репозитория Tailscale (Ubuntu noble), вход выполнен заказчиком через Google-аккаунт;
  снимок снят после установки и подключения (BackendState: Running, Self Online: true).
- XGW на шлюзе 0.1.15, а не 0.1.16, как ожидало ТЗ; заказчик разрешил продолжать без
  обновления (Т0 XGW не переустанавливает).
- Скрипт завершился с кодом 0, «проверка маскировки: чисто».
- На время программ заказчиком включён sudo без пароля (/etc/sudoers.d/99-zcode).
- Сырые данные снимка заказчик решил оставить в ~/xgw-ts-t0/raw (права 0700).
- Проверка секретов по §5: помимо допустимой строки 100.64.0.0/10 grep находит только
  100.100.100.100 (MagicDNS — константа из ТЗ, маскировка её сохраняет намеренно) и UUID
  UPnP роутера LAN — UUID заменён на [UUID-скрыт].

## Что не сделано и почему
- К3 не оценена на практике: шлюз не в режиме blocked (цепочки block_output нет), переводить
  шлюз в blocked Т0 запрещает. В остальных шагах отступлений от ТЗ нет.
