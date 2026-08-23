- [New] Producing classes on the well spine: `/v1/wells?producing=` scopes the collection to
      producing, not_producing or unknown, every well carries its class, and the class is
      defined by cr_producing_window_1, cr_producing_streams_1 and cr_producing_evidence_1
      rather than by a predicate in a query (R8); a class outside the three is refused
- [New] `/v1/wells/status-summary` counts the box by producing class, each count a figure with
      a derivation handle, beside `producing_window` stating the window, the qualifying
      streams and the oil+condensate liquids basis the counts are on
- [New] Producing read-out in the map legend: per-class counts with their own lineage handles,
      the window and basis stated beneath, and each class linking to the wells it counted
- [New] Migration 037 indexes canonical.production_monthly on production_month, which the
      window anchor reads once per request; it was a 288 ms sequential scan at 7.2M rows
- [Change] The producing window is anchored on the newest filed production month, never on the
         wall clock: the monthly report runs about five months behind, so a clock-anchored
         window would class every well not-producing
- [Change] A well that filed nothing in the window answers unknown, not not_producing, as does
         one whose months the regulator withheld and one in a jurisdiction that reports at the
         lease; only a filed zero or a hydrocarbon-free filing is not_producing
