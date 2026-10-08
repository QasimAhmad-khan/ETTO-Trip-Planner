# Five-minute fuel planner demo

1. Open [ETTO](https://etto-trip-planner.vercel.app/), select **Fuel Route Optimizer**, and plan Dallas, TX to Denver, CO with 50 gallons at departure. Show the map, station purchases, and total money spent.
2. In Postman, import `postman_fuel_collection.json`. Run **Health**, then **Dallas to Denver fuel route**. Point out `map_geojson`, `fuel_stops`, `total_money_spent_on_fuel_usd`, `fuel_consumed_gallons`, and `elapsed_ms`.
3. Run **Chicago to Los Angeles multiple fuel stops** and show how the route can require several purchases. Run the same-location request to demonstrate validation.
4. Explain the code in one minute: `fuel_routing.py` caches two US geocodes and one directions route; `fuel_optimizer.py` indexes route segments, projects the bundled station snapshot, and chooses fuel purchases; `fuel_views.py` returns the map and cost in one response. The supplied CSV lacks station coordinates, so GeoNames city centroids are used and detour costs are excluded.
5. Mention `python manage.py test trips` and `npm run build` as verification. Keep the Loom under five minutes and share its link with the repository.
