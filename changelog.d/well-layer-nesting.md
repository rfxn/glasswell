- [New] Layer panel: the Well spine group nests its four state well rows under one `Wells`
      parent switch, tri-state on `aria-pressed` (all on, all off, `mixed`), with the members
      shut on first paint and each reading by its state alone
- [Change] Layer labels state the state the same way on every row — `Wells (North Dakota)`,
           `Wells (Texas)`, `Survey traces (North Dakota)`, `Well paths (Montana)` and the
           six others — spelling the name out as the status page and the glossary already do
- [Fix] The North Dakota wells row was labelled `Wells`, unqualified, while Texas, New Mexico
      and Montana carried a state; first-ingested was reading to a reader as a distinction
- [Fix] Layer search finds a state by name: `texas` and `new mexico` matched no row, and
      `montana` matched only where a subtitle happened to spell it
- [Fix] Layer switch and opacity slider announce the standalone layer name under the nesting,
      so a screen reader hears `Show Wells (Texas)` rather than `Show Texas`
