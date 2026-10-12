"""Errors raised by the fuel route services, each mapped to an HTTP status."""


class FuelRouteError(Exception):
    status_code = 400
    code = "fuel_route_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidLocationError(FuelRouteError):
    status_code = 400
    code = "invalid_location"


class RoutingError(FuelRouteError):
    status_code = 502
    code = "routing_failed"


class NoFeasiblePlanError(FuelRouteError):
    status_code = 422
    code = "no_feasible_fuel_plan"
