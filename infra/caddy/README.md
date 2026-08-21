# infra/caddy — the TLS front door

DIR-13. Caddy terminates `https://glasswell.lab.rpx.sh` on VM 111 and reverse-proxies
uvicorn over `unix//run/glasswell/api.sock` — not a loopback port, because the TCP hop cost
~40 ms on every response under the loopback MSS (`../README.md` "Why the API has no port").
The certificate is a Let's Encrypt host certificate obtained
through the **DNS-01** challenge against the Cloudflare `rpx.sh` zone: the name resolves to
`192.168.2.111`, so no ACME server can reach an HTTP challenge on this host, and DNS-01 does
not care that the record is RFC1918 or two labels deep.

`Caddyfile` and `../systemd/caddy.service` are authoritative; `install.sh --with-caddy`
places them. The binary and the token file are one-time host state and are not in this
repository.

## The binary: a custom build, not the distro package, not xcaddy

The cloudflare DNS provider is a plugin, so stock Caddy cannot renew this certificate.
Three ways to get a binary that carries it:

| | Why not / why |
|---|---|
| `apt install caddy` | Ubuntu 24.04 ships **2.6.2** (2022) with no DNS provider modules at all. Rejected outright |
| `xcaddy build` | Needs a Go toolchain on the app VM and a rebuild at every upgrade, for a binary we do not modify. Rejected |
| download.caddyserver.com custom build | One static binary, no build tooling — and `caddy upgrade` re-downloads **with the same module set**, so an upgrade cannot silently drop the plugin the renewal depends on. Chosen |

The third-party apt repository has the opposite failure mode of the one that matters here:
`apt upgrade` would replace a plugin-carrying binary with a stock one, and nothing would go
wrong until the certificate came up for renewal 60 days later.

```bash
# install, and upgrade later, the same way
curl -fsSL -o /usr/local/bin/caddy.new \
  'https://caddyserver.com/api/download?os=linux&arch=amd64&p=github.com/caddy-dns/cloudflare'
chmod 0755 /usr/local/bin/caddy.new && mv /usr/local/bin/caddy.new /usr/local/bin/caddy
caddy list-modules | grep dns.providers.cloudflare     # the check that matters
systemctl restart caddy

caddy upgrade                                          # later: same modules, newer Caddy
```

`verify.sh` asserts the module is present, so a binary that lost it is a failed check rather
than a surprise at renewal time.

## The token

`/etc/caddy/cloudflare.env`, `root:root`, mode `0600`, one line:

```
CF_API_TOKEN=<a token with Zone:Read and DNS:Edit on rpx.sh>
```

It is read by systemd (as root) through `EnvironmentFile=` before Caddy drops to the `caddy`
user, so the file needs no group access. It is **not** in this repository and must not be —
the source of truth is the lab's `.secrets/cloudflare.env`. `install.sh --with-caddy` refuses
to run if the file is missing or its mode is wider than `0600`, and never prints it.

The shipped unit overrides upstream's `ExecStart`, which passes `--environ`: that flag prints
the whole environment, token included, into the journal at every start.

## What this config deliberately does not do

**No compression.** The origin already gzips text above 1 KiB, passes martin's zstd-encoded
tiles through untouched, and serves `basemap.pmtiles` identity-encoded so `Range` reads work.
Caddy's `encode` would at best duplicate that work and at worst re-encode an already-encoded
body, so it is absent.

**No security headers on the proxied path.** The API emits them on every response, including
its own 403s and 404s (`src/glasswell/api/security.py`). Adding `header` outside the basemap
block would *append* a second value, not replace the first — `curl -I` would show two
`X-Frame-Options`, and a CSP would be intersected. The rule is: the origin owns the policy,
the edge does not restate it.

`/basemap/*` is the one exception, because there the edge **is** the origin: the archive is
served from disk by `file_server` and uvicorn is not in the path. Those responses therefore
carry the policy written into the handler, and
`tests/unit/test_caddy_basemap_headers.py` asserts every value against
`glasswell.api.security` so the two copies cannot drift. Why the block exists at all — a
~40 ms Nagle stall per read on the proxy hop, with numbers — is in
`../basemap/README.md § Why Caddy serves this directly`.

**No HSTS.** `glasswell.lab.rpx.sh` is the break-glass path. Pinning a browser to HTTPS for
this name would remove the plain-HTTP fallback exactly when the certificate is the thing that
broke. The app's own CSP adds `upgrade-insecure-requests` when it sees `X-Forwarded-Proto:
https`, which covers mixed content without the durable pin.

**No `admin off`.** The admin API stays on its default `127.0.0.1:2019`, which is what makes
`systemctl reload caddy` a reload rather than a restart. `verify.sh` asserts it is loopback,
the same assertion martin gets.

## HTTP on :80

Automatic. Caddy answers `:80` for every site it serves with a `308` to the HTTPS origin, so
no redirect block appears above. A request to `http://192.168.2.111/` — the address, not the
name — matches no site and gets a Caddy 404; that is the correct answer for a certificate
that names one host.

## Renewal

Caddy renews at ~30 days remaining, on its own, with no timer of ours. Two things watch it:

- `caddy.service` carries `OnFailure=glasswell-alert@%n.service`, the same hook the API and
  the ingest units use — journal line at `daemon.err` plus a row in
  `/var/lib/glasswell/health-events`.
- `verify.sh` reads the served certificate with `openssl s_client` and fails when fewer than
  **20 days** remain. Caddy renews at 30, so a fail here means renewal has been failing for
  ten days — long before expiry, and visible on any run.
