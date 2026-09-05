- [Fix] The web glossary-seed helper resolves `glossary_seed.yml` from its own module rather
      than from the process CWD, so the card vocabulary gate and the R9 coverage gate read
      the committed seed from any working directory instead of only from `web/`
- [Fix] The changelog page is written inside the outDir the build resolved, not always into
      `web/dist`: a build into another directory no longer writes over the tree being
      served, and gets the page its own rail links to. A build that resolved no outDir
      refuses rather than guessing one
