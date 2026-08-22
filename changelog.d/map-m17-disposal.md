- [New] ND disposal and injection wells as a map layer (M1-7): a teal ring over the
      status dot for wells NDIC types SWD, WI, CO2I, AI, GI, SFI, MWUI or INJP —
      1,989 of 43,824 wells; off by default, gated at z8 with the thinned tiles,
      hover states the code as filed, legend names the class and its rule
- [New] cr_nd_well_type_disposal_1: the injection-class membership as a conformance
      row served at /v1/conformance, cited by the layer instead of owned by web code;
      seeded for fresh and deployed databases alike (migration 032)
- [Change] the ND wells tile mart, view and MVT now publish well_type_reported;
         nd_gis conform pass skips code_ref policy rows the same way nd_mpr does
- [Change] layer opacity sliders can name their paint property per style layer, so
         the disposal ring's slider drives its stroke rather than a transparent fill
