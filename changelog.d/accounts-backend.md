- [New] `GET /v1/sessions` lists every session the deployment holds a row for, owner-only and
      newest first, with the account, the role, the state against both windows, a coarse client
      label and an `address_class` of `lan`, `remote` or `unknown`. The address itself is not
      served: no ruling permits a client address in a body, so the row carries the class the
      screen actually reads and nothing more
- [New] `DELETE /v1/sessions/{session_id}` ends a session server-side. The owner may revoke any
      session; anyone else may revoke the one they are calling with, decided before any read so
      the route is not an existence oracle. Revoking twice answers the same record and writes
      one `session.ended`, because the event follows the rowcount rather than the request
- [New] `PATCH /v1/users/{user_id}` gains `state`, whose only accepted value is `active`.
      Disabling stays on `DELETE /v1/users/{user_id}`, which carries the owner floor and revokes
      the account's sessions; re-enabling an account that is already active is refused with
      `not_disabled` rather than answered silently, because the list that said otherwise is
      stale. The enable clears `disabled_at` and `disabled_by` together
- [New] `POST /v1/users` and `POST /v1/users/{user_id}/password` mint a password when the caller
      supplies none and return it once, on a `CreatedUser` model those two operations alone
      serve, with a `password_shown_once` warning. `UserModel` declares no password and a
      contract test keeps it that way — `/v1` is frozen additive, so a field published on the
      list schema is published for good
- [New] Migration `072_session_user_agent_family.sql` adds `lineage.sessions.user_agent_family`,
      written at login from the user-agent header, and a `(created_at desc, session_id desc)`
      index the newest-first list orders on. The stored fingerprint is one-way, so the label
      cannot be recovered at read time; rows created before the column are served as `unknown`
- [New] The users list carries `sessions_live`, counted against the injected clock rather than
      SQL `now()`, with its exemption reason stated in `non_figure_allowlist.yml` and beside the
      property in the served document
- [New] `session`, `role`, `owner` and `viewer` are seeded as glossary terms, all four
      `highlightable: false`: the highlighter compiles one app-wide regex over every served
      term, and four common words would gain underlines on every screen from a seed edit
- [Change] `new_password` joins the refused query parameters and is deleted by both Caddy log
           blocks, and the access-log filter now matches a credential-shaped parameter *inside*
           an identifier — `\b` before a bare `password` never fired on `new_password=`, because
           `_` is a word character. `monkey=` is redacted as collateral, which is the safe
           direction: a redacted log value is recoverable from the request, a leaked credential
           is not
- [Change] The two owner routes that hash a password charge a distinct `admin_write` rate bucket
           as their first statement, before the Argon2id call, rather than riding the 120/min
           interactive bucket a session already holds
- [Fix] The last-owner refusal names the field the caller sent: the pointer is a parameter of
      the guard, so the `DELETE` path — which has no body — no longer points at `/role`, a field
      that request never carried
- [New] Accounts is a section of the Status surface for an owner and for nobody else, at
      `?view=status#accounts`: the users list with role, creation, last sign-in and live
      sessions; add a user; reset a password; disable and re-enable; and the session list with
      a revoke. It is a section rather than a fourth header mode because the mode switch spends
      373 of the 390 px a phone has and a fourth button needs 46 more than exist
- [New] A minted password is rendered once, from the response that minted it, beside the
      server's own `password_shown_once` warning and behind a `data-gw-secret` hook a
      screenshot harness substitutes before it captures. It is never put in a URL, never sent
      back, and leaves the document entirely when the panel is dismissed
- [New] Disabling, resetting and revoking each open an inline `role="alertdialog"` naming what
      ends, and send nothing until the reader confirms; re-enabling asks nothing, because
      nothing ends. Every refusal renders the server's own `detail`, with the fields it named
      only when it named some
- [Change] `client.ts` gains `listUsers`, `createUser`, `updateUser`, `enableUser`,
           `disableUser`, `resetPassword`, `listSessions` and `revokeSession` over a private
           `mutateEnvelope`, which returns the whole envelope so a write can carry a warning;
           `mutate` is now that function unwrapped, so the one-shot CSRF re-challenge stays in
           one place. `main.ts` passes the role it already resolved into the Status surface
           rather than letting a second probe answer the same question
