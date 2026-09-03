- [Change] Colorado's six job schedules observe: the rows `077_colorado.sql` registered
           launching are superseded at 2026-09-03 by rows that record what a tick would run
           and start nothing, each under its own `cr_job_cadence_<job>_2` rule stating why and
           which preconditions it is waiting on; the founding rows stand as what was decided
           on 2026-09-02
- [Change] `launch_mode = 'launch'` is the scheduler launch-flip track's own act rather than a
           choice a jurisdiction makes at registration; the add-a-state and scheduler runbooks
           say so, and a seed guard reddens on any row that resolves to it
- [Fix] `infra/verify.sh` compares the scheduler role's flags against `false|true`, which is
      what `rolsuper || '|' || rolcanlogin` returns; it asserted psql's bare-column `f|t`
      rendering, so the check could never have passed against any role
- [Fix] The Status page's `What drives this` no longer opens on the sentence already in the
      Cadence cell beside it, which it repeated on 31 of 38 job rows
- [Fix] A command-line flag inside a cadence note is held on one line, so `--promote-design` is
      no longer shown to a reader broken after its first hyphen
- [Fix] A `Next due` the observation instant has already passed reads "Was due" rather than
      stating a future-tense fact about a past one
- [Fix] The positioning line beside the wordmark completes at the 820 rung signed out, where it
      was cut to `— NO NAKED NUM` with no ellipsis to mark it
- [Fix] An out-of-scale legend row recedes without taking its served count and derivation
      handle below the contrast floor, and the browser tier's contrast audit measures every
      match and reports the worst rather than the first it finds
- [Change] Four routers read each borrowed name from the module that defines it rather than
           through another router relaying it
