- [New] P3 model-ready `mdv1.2` persists three-stream cum12/cum24 labels,
      producing-month curves, DB-backed shared splits, and immutable coverage and
      rejection artifacts under one registered D1 recipe
- [Change] E-6 now measures the intermittency guard at 16 months over 22,023 matured
         North Dakota wells using the canonical three-stream producing-month rule
- [Fix] Incomplete labels remain assigned without moving split knowledge cutoffs, while
      withheld/confidential and completion-after-production subjects are explicitly
      excluded instead of silently entering train, calibration, or test
