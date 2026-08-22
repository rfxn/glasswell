- [New] deploy.sh stamps the code identity for lineage on every deploy: writes
      GLASSWELL_CODE_VERSION=<tag>+<commit> and GLASSWELL_LOCKFILE_SHA256 into
      /etc/glasswell/code-version.env, sourced last by glasswell-api.service and
      glasswell-ingest.service; verify.sh asserts the stamp is present
- [New] deploy.sh refuses when the repo carries migrations ahead of the database's
      schema_migrations head; --skip-migrations states the gap in a banner and proceeds
- [New] deploy.sh seeds the registries on every deploy (seed_all as postgres over the
      socket DSN, after migrate) so new conformance rules land before the first ingest
- [Fix] deploy.sh installs the tree's martin config to /etc/martin/config.yaml on every
      deploy, closing the drift verify.sh could only detect; usage now carries the
      canonical postgres-uid mart-refresh command with the code-version env
