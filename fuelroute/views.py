from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteRequestSerializer
from .services.exceptions import FuelRouteError
from .services.planner import plan_trip


class RoutePlanView(APIView):
    """Plan the cheapest fuel stops between two US locations.

    POST {"start": "Chicago, IL", "finish": "Los Angeles, CA"}
    or GET /api/route/?start=Chicago, IL&finish=Los Angeles, CA
    """

    def get(self, request):
        return self._plan(request, request.query_params)

    def post(self, request):
        return self._plan(request, request.data)

    def _plan(self, request, data):
        serializer = RouteRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        start, finish = serializer.validated_data["start"], serializer.validated_data["finish"]

        try:
            result = plan_trip(start, finish)
        except FuelRouteError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )

        query = urlencode({"start": start, "finish": finish})
        result["map_url"] = request.build_absolute_uri(f"{reverse('fuelroute:route-map')}?{query}")
        return Response(result)


def route_map_view(request):
    """HTML map (Leaflet + OpenStreetMap) of the route and fuel stops."""
    serializer = RouteRequestSerializer(data=request.GET)
    if not serializer.is_valid():
        return render(
            request,
            "fuelroute/map.html",
            {"error": "Provide ?start=...&finish=... (e.g. start=Chicago, IL&finish=Los Angeles, CA)."},
            status=400,
        )

    try:
        result = plan_trip(
            serializer.validated_data["start"], serializer.validated_data["finish"]
        )
    except FuelRouteError as exc:
        return render(request, "fuelroute/map.html", {"error": exc.message}, status=exc.status_code)

    return render(request, "fuelroute/map.html", {"result": result})
