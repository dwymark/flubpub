# flubpub reverse SSH tunnel

Standing remote SSH access to the **home machine** (WSL, user `dwymark`) via a
reverse tunnel terminated on the flubpub VPS (`danielwymark.com`). This is
option 3 from the access digest: no third-party mesh, the tunnel is anchored
*inside* WSL so there's no Windows-side `netsh portproxy` hop.

```
  [ work laptop ] --ssh :47022--> danielwymark.com --(reverse tunnel)--> [ home WSL sshd :22 ]
```

The home box runs `autossh` under systemd, dialling out to the VPS and asking it
to bind `0.0.0.0:47022` and forward it back home. Because it's an *outbound*
connection from home, no router port-forward or WSL2 NAT gymnastics are needed.

## Pieces

| File | Lives on | Role |
|------|----------|------|
| `flubpub-tunnel.service.template` | home | systemd unit (autossh), rendered by the script |
| `sshd-tunnel.conf` | VPS | `GatewayPorts clientspecified` drop-in so the `-R 0.0.0.0:` bind is allowed |
| `setup-tunnel.sh` | run on home | idempotent installer for both ends |

## Install / update

```bash
bash deploy/tunnel/setup-tunnel.sh
# override defaults if needed:
TUNNEL_PORT=47022 REMOTE_HOST=danielwymark.com bash deploy/tunnel/setup-tunnel.sh
```

## Use from a remote machine

```bash
ssh -p 47022 dwymark@danielwymark.com
```

Password auth is on today. **Switch to keys** by appending your work machine's
public key to `~/.ssh/authorized_keys` on the home box, then set
`PasswordAuthentication no` in the home sshd config.

## Operate

```bash
systemctl status flubpub-tunnel        # on home
journalctl -u flubpub-tunnel -f        # tunnel logs
sudo systemctl restart flubpub-tunnel
bash deploy/tunnel/setup-tunnel.sh --down   # stop + remove both ends
```

## Security notes

- The forwarded port exposes **password-auth SSH to the public internet** until
  keys replace it. `47022` is a high nonstandard port (cuts drive-by noise, not
  a real control). Move to key-only auth promptly; consider `fail2ban` on the
  home sshd if this stays up.
- `GatewayPorts clientspecified` only lets a client that *explicitly* requests a
  wildcard bind get one; plain `-R` forwards still bind loopback. Nothing else
  loosened.
- The tunnel runs as `dwymark` and authenticates to the VPS with
  `~/.ssh/id_rsa` (already trusted by `root@danielwymark.com`).
- ufw is inactive on the VPS; if a DigitalOcean **cloud firewall** is ever
  attached, port 47022 must be opened there too — the script can't reach it.
