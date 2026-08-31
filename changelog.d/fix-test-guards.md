- [Fix] tests: the R6 naked-numbers gate classifies a figure by the value of its `d` rather than
      by the key's presence, and a handle position carrying a null or non-string value is now
      reported as an offender instead of being skipped. Serving `d: null` on every figure in
      the API left all eleven checks green, with the non-emptiness guard held up by the
      `_lineage` sidecars
- [Fix] tests: the login bound's ordering assertion counts Argon2id verifies on
      `accounts.verify_password` rather than reading the status code. Authenticate-then-limit
      and limit-then-authenticate both answer 429, so the status assertion was satisfied by a
      route that ran a full 64 MiB verify for every unauthenticated attempt and refused
      afterwards — the amplification the bound exists to stop
- [Fix] tests: the constant-time guards read the parsed module. `hmac.compare_digest` must appear
      as a call node rather than anywhere in the source text, and each `==` operand is followed
      back through the renames that bound it, so `_a, _b = presented, owner_key` no longer hides
      a variable-time comparison of the owner API key from the name allowlist
- [Fix] tests: the layer-boundary guards fold every string a module builds — concatenations and
      f-string parts alike — before searching it, so a schema name written in pieces is judged
      on the value it executes as. Applied to the feature matrix, the whole marts package, the
      Montana and New Mexico marts and the New Mexico wells GIS walk
- [Fix] tests: the producing-summary omission check is driven from the collection and asserts set
      equality, so a class the summary drops is visited rather than never iterated, and the box
      is seeded a second class so an omission has something to omit
- [Fix] tests: the `/v1/keys` at-rest scan reads every column rather than `sha256, label`, and
      names the column a cleartext key reached; the claim was "sha256 is the only representation
      at rest" while two of ten columns were looked at
- [Fix] tests: non-emptiness guards on the glossary label, conformance rationale, quarantine
      metric, stored session hash and status-bucket assertions, each of which an empty
      collection made vacuously true
- [Fix] tests: the selector registry fixtures pin `output_sha256` as a literal rather than
      computing it with the same function the implementation compares against, and a mismatched
      evidence hash is asserted to be refused
- [Fix] web: the overlay restore test asserts focus lands on the body when the restore target has
      left the document, rather than asserting a different element is still attached. `.focus()`
      on a detached element is a silent no-op, so dropping the `isConnected` guard stranded
      focus inside the panel that had just closed with all nine tests green
