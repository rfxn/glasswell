- [Fix] The web glossary-seed helper resolves `glossary_seed.yml` from its own module rather
      than from the process CWD, so the card vocabulary gate and the R9 coverage gate read
      the committed seed from any working directory instead of only from `web/`
