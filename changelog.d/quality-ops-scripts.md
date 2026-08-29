- [Fix] verify.sh: an empty tile roster and an unparseable martin catalogue are each
      their own named failure rather than compared to each other; both sides came from
      a command whose stderr is suppressed, so a venv that cannot import the marts and
      a martin that answered nothing read as ok while the per-layer loop ran zero times
- [Change] verify.sh: the deploy-hygiene sweep reads compgen output line by line rather
         than word-splitting it, so a stray path containing a space stays one path
