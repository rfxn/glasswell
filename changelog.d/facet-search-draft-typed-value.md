- [Fix] The "Wells by …" search box carries what the reader has typed across the rebuild its own
      commit causes, not their caret alone. The rebuilt box is filled from the URL, which lags
      the keyboard by a 250 ms debounce plus a round trip, so a reader typing slower than that —
      anyone recalling an operator name — lost every letter after the second and lost the box
      with them: measured on a branch instance at 300 ms a character, `energy` arrived as `en`
      with `document.activeElement` back on `BODY`, and the rest of the word went nowhere. Fast
      typing never saw it, because every keystroke landed inside one debounce window and only
      one commit ever fired. The word the reader is mid-way through now survives the rebuild,
      the caret sits where they left it, and no other control on the panel — dimension, state,
      sort, cut or a bucket press — pulls them back into the box it rebuilt
