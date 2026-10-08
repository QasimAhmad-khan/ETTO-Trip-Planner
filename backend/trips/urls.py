from django.urls import path
from .views import TripPlanView, HealthCheckView
from .fuel_views import FuelRouteView

urlpatterns = [
    path("trips/plan", TripPlanView.as_view(), name="trip-plan"),
    path("health", HealthCheckView.as_view(), name="health"),
    path("fuel/route", FuelRouteView.as_view(), name="fuel-route"),
]
