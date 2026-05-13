select distinct
subroute_num
  from sites
  join routes on routes.id = sites.route_id
  left join cdps on cdps.site_id = sites.id
  left join leases cdp_leases on cdp_leases.id = cdps.lease_id
  left join facilities on cdps.facility_id = facilities.id
  left join wells on wells.site_id = sites.id
  left join leases well_leases on well_leases.id = wells.lease_id
WHERE (:route_id      IS NULL OR :route_id      = 0 OR routes.id      = :route_id)
  AND (:site_id       IS NULL OR :site_id       = 0 OR sites.id       = :site_id)
  AND (:subroute_num  IS NULL OR :subroute_num  = 0 OR subroute_num  = :subroute_num)
  AND (:lease_id      IS NULL OR :lease_id      = 0 OR cdp_leases.id      = :lease_id OR well_leases.id      = :lease_id)
  AND (:facility_id   IS NULL OR :facility_id   = 0 OR facilities.id   = :facility_id)
  AND (:well_id       IS NULL OR :well_id       = 0 OR wells.id       = :well_id)
  and subroute_num IS NOT NULL
  order by subroute_num