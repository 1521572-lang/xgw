"""One bounded HTTPS sample from an authorized Linux LAN client."""

import ipaddress
import json
import subprocess

URL = "https://www.cloudflare.com/cdn-cgi/trace"
FORMAT = ('{"http":"%{http_code}","bytes":%{size_download},"local_ip":"%{local_ip}",'
          '"local_port":%{local_port},"remote_ip":"%{remote_ip}"}')


def sample():
    transfer = subprocess.run(
        ["curl", "-q", "--noproxy", "*", "--ipv4", "--http1.1", "--connect-timeout", "4",
         "--max-time", "8", "--max-filesize", "4096", "--silent", "--output", "/dev/null",
         "--write-out", FORMAT, URL], capture_output=True, text=True, timeout=10, check=False,
    )
    result = json.loads(transfer.stdout)
    result["http"] = int(result["http"])
    result["curl_rc"] = transfer.returncode
    result["next_hop"] = None
    if result["local_ip"] and result["remote_ip"]:
        source = str(ipaddress.IPv4Address(result["local_ip"]))
        peer = str(ipaddress.IPv4Address(result["remote_ip"]))
        routes = subprocess.run(["ip", "-j", "-4", "route", "get", peer, "from", source],
                                capture_output=True, text=True, timeout=2, check=False)
        if routes.returncode == 0:
            entries = json.loads(routes.stdout)
            if len(entries) == 1:
                result["next_hop"] = entries[0].get("gateway")
    return result


if __name__ == "__main__":
    try:
        result = sample()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print('{"state":"client_sample_unavailable"}')
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True))
