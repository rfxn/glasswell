- [Fix] cloudflared: the connector unit declared `Type=notify`, but `tunnel run` serves
      without ever sending sd_notify READY, so systemd held it in `activating`, timed the
      start out and restarted a working tunnel — 49 restarts against four registered QUIC
      connections; now `Type=exec`
- [Fix] install.sh: make `/etc/cloudflared` group-traversable, since 0640 root:cloudflared
      files are unreadable through a 0700 root:root parent and the connector reports the
      file rather than the directory that refused it
