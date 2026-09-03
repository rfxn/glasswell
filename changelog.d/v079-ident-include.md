- [Fix] install.sh writes the pg_ident include as a bare filename; an HBA or ident include
      takes no quotes, and PostgreSQL read the quoted postgresql.conf form as a name with
      quotes in it, so the usermap loaded empty and every peer login but postgres was
      refused on a host that had taken the map; a re-run now corrects a host that received
      the quoted line, and the unit test asserts the name resolves rather than pinning the
      string install.sh happens to write
