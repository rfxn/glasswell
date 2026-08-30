- [Fix] deploy.sh: install every configured layer's tile function after seeding and before
      the martin restart. martin refuses to boot on an unresolvable source, so three New
      Mexico and boundary layers whose marts had never been refreshed stopped it starting
      and took nd_wells and tx_wells down with them
