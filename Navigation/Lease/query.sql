select distinct
leases.id,
lease_name
  from leases
  left join cdps on cdps.lease_id = leases.id
  left join wells on wells.lease_id = leases.id
  left join sites on sites.id = cdps.site_id
  left join routes on routes.id = sites.route_id
WHERE (:route_id      IS NULL OR :route_id      = 0 OR sites.route_id      = :route_id)
  AND (:site_id       IS NULL OR :site_id       = 0 OR cdps.site_id       = :site_id)
  AND (:subroute_num  IS NULL OR :subroute_num  = 0 OR sites.subroute_num  = :subroute_num)
  AND (:lease_id      IS NULL OR :lease_id      = 0 OR cdps.lease_id      = :lease_id)
  AND (:facility_id   IS NULL OR :facility_id   = 0 OR cdps.facility_id   = :facility_id)
  AND (:well_id       IS NULL OR :well_id       = 0 OR wells.id       = :well_id)
  order by lease_name