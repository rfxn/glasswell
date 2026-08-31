- [Fix] The login ordering test no longer walks the address bucket to its limit through the
      route. Twenty-one requests at the 250 ms login floor is a multi-second loop against a
      limiter window that is a truncated UTC minute, so a run that crossed a boundary met a
      reset counter and the last request answered 403 rather than 429; seven of the last
      twenty CI runs on main failed that way and v0.69 was tagged red. It now seeds the
      bucket and asserts the same 403-then-429 pair in two requests
- [Fix] test_the_index_is_rate_limited asserts both edges of the type-curve index ceiling
      against the shipped constant rather than walking thirty-one requests to it, which
      carried the same window race with no margin
- [New] await_rate_window, rate_window_remaining and spend_rate_window hold the limiter's
      current window open for the request under test, measured on the database clock the
      limiter reads rather than the runner's; fill_bucket waits through a boundary that is
      about to fall, and test_a_seeded_bucket_outlives_the_request_it_was_seeded_for goes
      red if that wait is removed
