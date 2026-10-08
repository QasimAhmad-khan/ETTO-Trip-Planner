from rest_framework import serializers
import math

class TripPlanSerializer(serializers.Serializer):
    current_location = serializers.CharField(required=True, allow_blank=False)
    pickup_location = serializers.CharField(required=True, allow_blank=False)
    dropoff_location = serializers.CharField(required=True, allow_blank=False)
    current_cycle_used = serializers.FloatField(required=True, min_value=0.0, max_value=70.0)
    use_ym = serializers.BooleanField(default=True)
    use_pc = serializers.BooleanField(default=False)
    start_time = serializers.DateTimeField(required=False, format="%Y-%m-%dT%H:%M:%S")

    def validate_current_cycle_used(self, value):
        return round(value, 1)


class FuelRouteSerializer(serializers.Serializer):
    start = serializers.CharField(min_length=2, max_length=200, trim_whitespace=True)
    finish = serializers.CharField(min_length=2, max_length=200, trim_whitespace=True)
    starting_fuel_gallons = serializers.FloatField(default=50.0, min_value=0, max_value=50)

    def validate(self, attrs):
        if attrs["start"].casefold() == attrs["finish"].casefold():
            raise serializers.ValidationError("Start and finish must differ.")
        if not math.isfinite(attrs["starting_fuel_gallons"]):
            raise serializers.ValidationError("Starting fuel must be a finite number.")
        return attrs
