# core/models.py
from django.db import models

class Region(models.Model):
    region_code = models.CharField(max_length=20, primary_key=True)
    region_name = models.CharField(max_length=50)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    grid_nx = models.IntegerField()
    grid_ny = models.IntegerField()

    def __str__(self):
        return self.region_name