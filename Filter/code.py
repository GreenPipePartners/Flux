class NavigationFilter:
    from collections import namedtuple

    Action = namedtuple(
        'Action', 
        ["category", "clear", "filter", "define"]
        )

    site_action = {
        4: Action("lease", False, True, False),
        5: Action("well", True, True, False),
        3: Action("site", False, 'upstream', True),
        1: Action("subroute", False, False, True),
        2: Action("route", False, False, True),
        6: Action("facility", False, False, True)
    }
    site_order = [
        'route',
        'subroute',
        'site',
    ]
    site_nav_order = [
        # 'route',
        'subroute',
        'site',
    ]

    subroute_action = {
        5: Action("lease", False, True, True),
        4: Action("well", True, True, True),
        3: Action("site", True, True, True),
        1: Action("subroute", False, False, False),
        2: Action("route", False, False, True),
        6: Action("facility", True, False, False)
    }
    subroute_order = [
        'route',
        'subroute', 
    ]
    subroute_nav_order = [
        # 'route',
        'subroute', 
    ]

    route_action = {
        5: Action("lease", False, True, True),
        4: Action("well", True, True, True),
        3: Action("site", True, True, True),
        1: Action("subroute", False, False, True),
        2: Action("route", False, False, True),
        6: Action("facility", True, False, False)
    }
    route_order = ['route']
    route_nav_order = ['route']

    well_action = {
        5: Action("lease", False, True, False),
        4: Action("well", False, 'upstream', True),
        3: Action("site", True, 'upstream', True),
        2: Action("subroute", False, False, True),
        1: Action("route", False, False, True),
        6: Action("facility", True, False, False)
    }
    well_order = [
        'route',
        'subroute',
        'site',
        'well',
    ]
    well_nav_order = [
        # 'route',
        'subroute',
        'site',
        'well',
    ]

    facility_action = {
        2: Action("lease", True, True, True),
        4: Action("well", False, False, False),
        3: Action("site", True, True, True),
        5: Action("subroute", True, False, False),
        6: Action("route", True, False, False),
        1: Action("facility", False, False, False)
    }
    facility_order = ['facility']
    facility_nav_order = ['facility']

    lease_action = {
        1: Action("lease", False, False, False),
        4: Action("well", True, False, False),
        3: Action("site", True, True, True),
        5: Action("subroute", True, False, False),
        6: Action("route", True, False, False),
        2: Action("facility", False, False, True)
    }
    lease_order = [
        'facility', 
        'lease',
    ]
    lease_nav_order = [
        'facility', 
        'lease',
    ]

    clear_action = {
        1: Action("lease", True, True, False),
        4: Action("well", True, True, False),
        3: Action("site", True, True, False),
        5: Action("subroute", True, True, False),
        6: Action("route", True, True, False),
        2: Action("facility", True, True, False)
    }
    navigation_labels = {
        "site": {'table': 'sites', 'name_field': 'site_name'},
        "subroute": {'table': 'sites', 'name_field': 'subroute_num'},
        "route": {'table': 'routes', 'name_field': 'route_name'},
        "well": {'table': 'wells', 'name_field': 'well_name'},
        "facility": {'table': 'facilities', 'name_field': 'facility_name'},
        "lease": {'table': 'leases', 'name_field': 'lease_name'},
    }


    def __init__(self, current_filters, current_options, category, call_context):
        self.query_count = 0
        self.current_filters = current_filters
        self.category = category
        self.query_dict = {
            "lease": self.lease_query,
            "well": self.well_query,
            "site": self.site_query,
            "subroute": self.subroute_query,
            "route": self.route_query,
            "facility": self.facility_query,
        }
        self.current_options = current_options if current_options else {key: None for key in self.query_dict}

        self.action_dict = {
            "site": self.site_action,
            "subroute": self.subroute_action,
            "route": self.route_action,
            "well": self.well_action,
            "facility": self.facility_action,
            "lease": self.lease_action,
            "clear": self.clear_action,
        }

        self.order_dict = {
            "site": self.site_order,
            "subroute": self.subroute_order,
            "route": self.route_order,
            "well": self.well_order,
            "facility": self.facility_order,
            "lease": self.lease_order,
        }
        self.nav_order_dict = {
            "site": self.site_nav_order,
            "subroute": self.subroute_nav_order,
            "route": self.route_nav_order,
            "well": self.well_nav_order,
            "facility": self.facility_nav_order,
            "lease": self.lease_nav_order,
        }
        self.current_order = self.order_dict[category] if category != 'clear' else []

        for idx, category in enumerate(self.current_order):
            if not self.current_filters[category]:
                continue
            if self.current_filters[category] not in self.current_options[category].getColumnAsList(0):
                filters = {key: None if key not in self.current_order[0:idx] else val for key, val in self.current_filters.items()}
                self.current_options[category] = self.query_dict[category](**filters)

        self.current_action_matrix = self.action_dict[category]
        self.updated_filters = self.update_navigation()[0]

    def next_prev_filters(self):
        next_id, next_category = self.next_query(self.category)
        prev_id, prev_category = self.prev_query(self.category)


        # 2. To get the 'next' state, we temporarily update current_filters
        # and run the update_navigation logic to see the resulting cascade.
        
        # Helper to simulate a navigation change
        def simulate_navigation(target_id, target_cat, prev_next):
            # Save original state
            original_filters = self.current_filters.copy()
            original_cat = self.category
            
            # Inject the new ID and update the category to trigger the right matrix
            self.current_filters[target_cat] = target_id
            self.category = target_cat
            self.current_action_matrix = self.action_dict[target_cat]
            
            # Run the update logic to get the cascaded results
            new_filters, _ = self.update_navigation()


            
            # Restore original state so this instance remains pure
            self.current_filters = original_filters
            self.category = original_cat
            self.current_action_matrix = self.action_dict[original_cat]
            
            return new_filters


        next_filter = simulate_navigation(next_id, next_category, 'next')
        prev_filter = simulate_navigation(prev_id, prev_category, 'prev')
        if self.category != next_category:
            order_cycler = self.current_order[self.current_order.index(next_category)+1:self.current_order.index(self.category)+1]
            next_filter = {key: None if key in order_cycler else val for key, val in next_filter.items()}
            for cat in order_cycler:
                if cat == 'subroute':
                    next_filter[cat] = 1
                else:
                    next_filter[cat] = self.query_dict[cat](**next_filter).getValueAt(0,0)
        if self.category != prev_category:
            order_cycler = self.current_order[self.current_order.index(prev_category)+1:self.current_order.index(self.category)+1]
            prev_filter = {key: None if key in order_cycler else val for key, val in prev_filter.items()}
            for cat in order_cycler:
                if cat == 'subroute':
                    prev_filter[cat] = 4
                else:
                    try:
                        prev_filter[cat] = self.query_dict[cat](**prev_filter).getColumnAsList(0)[-1]
                    except:
                        prev_filter[cat] = None

        next_filter['field'] = 1
        prev_filter['field'] = 1
        return (next_filter, prev_filter)

    def update_navigation(self):
        self.cleared_filters = self.clear_filter_dict()
        self.filters = self.cleared_filters
        for num in range(1, len(self.current_action_matrix) + 1):
            self.filters = self.query_and_update_filters(self.current_action_matrix[num].category, self.filters)
        for action in self.current_action_matrix.values():
            if action.filter and action.filter != 'upstream':
                self.current_options[action.category] = self.query_dict[action.category](**self.filters)
            if action.filter == 'upstream':
                idx = self.current_order.index(action.category)
                _filters = {}
                for key, val in self.filters.items():
                    _filters[key] = val if key in self.current_order and self.current_order.index(key) < idx else None
                self.current_options[action.category] = self.query_dict[action.category](**_filters)
        for key, val in self.filters.items():
            if val is None:
                continue

            if val not in self.current_options[key].getColumnAsList(0):
                system.perspective.print('value: %s not found in current_options list: %s for category: %s'%(val, self.current_options[key].getColumnAsList(0), key))
        return (self.filters, self.current_options)

    def clear_filter_dict(self):
        clear_current_filters = {}
        for order, action in self.current_action_matrix.items():
            clear_current_filters[action.category] = None if action.clear else self.current_filters[action.category]
        return clear_current_filters

    def query_and_update_filters(self, category, filters):
        dataset = self.query_dict[category](**filters)
        for val in self.current_action_matrix.values():
            if val.category == category:
                define = val.define
                break
        if dataset.getRowCount() == 1 and define:
            filters[category] = dataset.getValueAt(0, 0)
        return filters

    def next_query(self, category):
        current_id = self.updated_filters[category]
        current_options = self.current_options[category]
        category_order = self.nav_order_dict[category]
        last_row_idx = current_options.getRowCount() - 1 if current_options.getRowCount() > 0 else 0
        if category == 'subroute' and current_id == 4:
            if category_order.index(category) == 0:
                return (1, category)
            else:
                return self.next_query(category_order[category_order.index(category) - 1])
        if current_options.getValueAt(last_row_idx,0) == current_id:
            if category_order.index(category) == 0:
                return (current_options.getValueAt(0,0), category)
            else:
                return self.next_query(category_order[category_order.index(category) - 1])
        for i in range(current_options.getRowCount()):
            if current_options.getValueAt(i,0) == current_id:
                return (current_options.getValueAt(i+1,0), category)
        return (None, category)

    def prev_query(self, category):
        current_id = self.updated_filters[category]
        current_options = self.current_options[category]
        category_order = self.nav_order_dict[category]
        if category == 'subroute' and current_id == 1:
            if category_order.index(category) == 0:
                return (4, category)
            else:
                return self.prev_query(category_order[category_order.index(category) - 1])

        if current_options.getValueAt(0,0) == current_id:
            if category_order.index(category) == 0:
                return (current_options.getValueAt(current_options.getRowCount()-1,0), category)

            else:
                return self.prev_query(category_order[category_order.index(category) - 1])
        for i in range(current_options.getRowCount()):
            if current_options.getValueAt(i,0) == current_id:
                return (current_options.getValueAt(i-1,0), category)
        return (None, category)

    def lease_query(self, lease, well, site, subroute, route, facility):
        params = {
            "lease_id": lease,
            "well_id": well,
            "site_id": site,
            "subroute_num": subroute,
            "route_id": route,
            "facility_id": facility,
        }
        self.query_count += 1
        return system.db.runNamedQuery('Navigation/Lease', params)

    def well_query(self, lease, well, site, subroute, route, facility):
        params = {
            "lease_id": lease,
            "well_id": well,
            "site_id": site,
            "subroute_num": subroute,
            "route_id": route,
            "facility_id": facility,
        }
        self.query_count += 1
        return system.db.runNamedQuery('Navigation/Well', params)

    def site_query(self, lease, well, site, subroute, route, facility):
        params = {
            "lease_id": lease,
            "well_id": well,
            "site_id": site,
            "subroute_num": subroute,
            "route_id": route,
            "facility_id": facility,
        }
        self.query_count += 1
        return system.db.runNamedQuery('Navigation/Site', params)

    def subroute_query(self, lease, well, site, subroute, route, facility):
        params = {
            "lease_id": lease,
            "well_id": well,
            "site_id": site,
            "subroute_num": subroute,
            "route_id": route,
            "facility_id": facility,
        }
        self.query_count += 1
        return system.db.runNamedQuery('Navigation/Subroute', params)

    def route_query(self, lease, well, site, subroute, route, facility):
        params = {
            "lease_id": lease,
            "well_id": well,
            "site_id": site,
            "subroute_num": subroute,
            "route_id": route,
            "facility_id": facility,
        }
        self.query_count += 1
        return system.db.runNamedQuery('Navigation/Route', params)

    def facility_query(self, lease, well, site, subroute, route, facility):
        params = {
            "lease_id": lease,
            "well_id": well,
            "site_id": site,
            "subroute_num": subroute,
            "route_id": route,
            "facility_id": facility,
        }
        self.query_count += 1
        return system.db.runNamedQuery('Navigation/Facility', params)