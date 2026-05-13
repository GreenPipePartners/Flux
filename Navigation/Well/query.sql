select distinct
wells.id,
well_name
  from wells
  left join leases on leases.id = wells.lease_id
  left join sites on sites.id = wells.site_id
  left join routes on sites.route_id = routes.id
WHERE (:route_id      IS NULL OR :route_id      = 0 OR routes.id      = :route_id)
  AND (:site_id       IS NULL OR :site_id       = 0 OR sites.id       = :site_id)
  AND (:subroute_num  IS NULL OR :subroute_num  = 0 OR sites.subroute_num  = :subroute_num)
  AND (:lease_id      IS NULL OR :lease_id      = 0 OR leases.id      = :lease_id)
  AND (:well_id       IS NULL OR :well_id       = 0 OR wells.id       = :well_id)
  order by well_name