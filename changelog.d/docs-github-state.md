- [Fix] The architecture document, contributing rules and architecture diagram name the
      served `/v1/quarantine` path and the real `staging.` table families, replacing a
      `/quality` namespace and a `stg_` naming convention the schema never used
- [Change] The architecture document separates resident marts and data-model tables from
         contracted ones, and names the systemd timers the deployed host actually runs
- [Change] Status and roadmap record the deployed recurring restore drill's own verified
         pass, and the resident reverse-FK index and completed neighbour replay, in place
         of the deployment gaps those items had been carrying
- [Change] The README API block covers every served operation family, and the project docs
         table links the two P3 evidence documents that only prose had referenced
