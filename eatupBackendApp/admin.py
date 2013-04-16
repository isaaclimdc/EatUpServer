from django.contrib import admin
from eatupBackendApp.models import AppUser, Event, Location, DumbLocation

'''
class EventLocationsInline(admin.StackedInline):
    model = Location
    extra = 0
'''

class EventDumbLocationsInline(admin.StackedInline):
    model = DumbLocation
    extra = 0
    
class EventAdmin(admin.ModelAdmin):
    inlines = [EventDumbLocationsInline] #[EventLocationsInline]
    list_display = ('eid', 'title', 'date_time')

class AppUserAdmin(admin.ModelAdmin):
    list_display = ('uid', 'last_name', 'first_name')
  
'''  
class LocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'lat', 'lng', 'friendly_name', 'eventHere')
'''  
  
class DumbLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'friendly_name')
  
# makes these models available on the admin console
admin.site.register(Event, EventAdmin)
admin.site.register(AppUser, AppUserAdmin)
#admin.site.register(Location, LocationAdmin)
admin.site.register(DumbLocation, DumbLocationAdmin)