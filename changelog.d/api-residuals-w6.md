- [New] /v1/wells serves geometry_provenance on every collection item — the distinct
      classes of the well's recorded geometry, canonical geom_type verbatim under
      cr_nd_geometry_provenance_1 — and gains the matching filter, verbatim equality
      on any of the well's geometry, wired into the cursor fingerprint and the served
      next link with both refusal directions under test (m13 residual, the R-1 pattern)
- [New] /v1/wells/status-summary classes the box two more ways: wells per
      geometry-provenance class and per reported well-type code, each a figure with
      its own handle and the classing rule linked, so registry coverage statements
      (traced wells, disposal-code counts) derive from the API instead of pinned
      constants (m13 residual / m17 R-3)
- [Change] api follow-on residuals closed in the test tier: the vintages page-link
         byte assertion now derives from the page's own promotions and is proven
         against a second seeded promotion rather than depending on the single-
         promotion fixture (RN-2), and the parser-symmetric fragment shapes
         (%23h=, #h%3D, ##h=) are documented as naming no h key to any parser,
         with their decoded neighbours proven refused (RN-1)
