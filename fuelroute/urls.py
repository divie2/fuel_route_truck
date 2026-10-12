from django.urls import path

from . import views

app_name = "fuelroute"

urlpatterns = [
    path("route/", views.RoutePlanView.as_view(), name="route-plan"),
    path("route/map/", views.route_map_view, name="route-map"),
]
