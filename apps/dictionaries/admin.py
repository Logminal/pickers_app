from django.contrib import admin

from .models import FurnitureType, PriceListItem, Region, Specialization

admin.site.register(FurnitureType)
admin.site.register(Region)
admin.site.register(Specialization)
admin.site.register(PriceListItem)
