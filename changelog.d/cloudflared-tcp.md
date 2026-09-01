- [Change] The tunnel connector runs `protocol: http2` instead of the QUIC default, and
           `infra/install.sh` places `/etc/sysctl.d/99-cloudflared-udp.conf` raising
           `net.core.rmem_max`/`wmem_max` to 7.5 MB — cloudflared asks quic-go for 7 MiB and
           logged `failed to sufficiently increase receive buffer size` against the 208 kiB
           default at every start. On an uplink that drops out for tens of seconds at a
           time, QUIC's idle timeout tore the tunnel down 1,919 times in six hours and the
           edge answered 530; TCP rides the same outages without re-registering. Remove the
           `protocol` line once the link is stable
