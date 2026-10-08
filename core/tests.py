from django.test import TestCase

# Create your tests here.
from .geo import latlng_to_grid


class LatLngToGridTests(TestCase):
    def test_seoul_city_hall(self):
        self.assertEqual(latlng_to_grid(37.5665, 126.9780), (60, 127))

    def test_busan_city_hall(self):
        self.assertEqual(latlng_to_grid(35.1798, 129.0750), (98, 76))