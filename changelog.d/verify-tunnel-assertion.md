- [Fix] verify.sh asserted that a caddy tunnel listener exists rather than that any listener
      on 8080 is loopback-bound, so a host with nothing on 8080 failed the deploy gate with
      a message claiming a binding it did not have; the negative stays unconditional
- [Fix] the documented glasswell-owner-bootstrap and glasswell-owner-reset commands run as
      root, where peer authentication resolves the role `root` and the connection fails
      before the password prompt; both now carry runuser -u glasswell
