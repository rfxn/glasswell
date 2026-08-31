- [Fix] The auth matrix status-probes the six routes it used to skip. `POST /v1/session`,
      `POST /v1/session/password` and the four `/v1/users` mutations sat in the table for
      coverage and outside the status assertions, which is 54 of the suite's 55 skips and one
      hole: what an anonymous, invalid-key, revoked-key or expired-session caller receives
      from a user-administration route was asserted nowhere, and the four `/v1/users` rows had
      been that way since the commit that added them. All 54 answer 403, or 200 for the owner
- [New] A matrix row carries an optional request body, and the login row carries a CSRF token
      bound to a pre-session nonce, so a POST, PATCH or DELETE case can be dispatched at all.
      `NOT_STATUS_PROBED` is gone rather than shorter
- [New] test_an_anonymous_caller_is_refused_before_their_body_is_read holds the five gated
      body-taking routes to answering 403 and not 422. A validation body names the schema it
      was validated against, and an uncredentialled caller's payload is never examined; the
      test goes red when a route's gate moves out of the dependency tree into the handler
- [Change] The matrix's principals speak https, including the key classes. A `__Host-` cookie
           requires Secure, so over http the transport drops it and a key-class caller could
           never hold the pre-session CSRF cookie the login row needs
- [Change] Each POST row states its own body instead of every POST being handed the key-issue
           one. `POST /v1/keys/{key_id}/rotate` takes no body and was being sent one, and a
           body shared by rows that do not share a schema hides which row needs what
