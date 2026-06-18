from rest_framework import serializers

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
