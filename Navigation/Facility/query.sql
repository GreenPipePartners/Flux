select distinct
facilities.id,
facility_name
  from facilities
  join cdps on cdps.facility_id = facilities.id
  
WHERE (:site_id       IS NULL OR :site_id       = 0 OR cdps.site_id       = :site_id)
  AND (:lease_id      IS NULL OR :lease_id      = 0 OR cdps.lease_id      = :lease_id)
  AND (:facility_id   IS NULL OR :facility_id   = 0 OR facilities.id   = :facility_id)
order by facility_name