from django.contrib import admin
from core.models import Ticket, TrainStation, Railroad


class TicketAdmin(admin.ModelAdmin):
	readonly_fields = (
		'origin',
		'destination',
		'path',
		'enter_station',
		'entered_at',
		'exit_station',
		'exited_at',
		'price'
	)

class TrainStationAdmin(admin.ModelAdmin):
    exclude = ('cluster',)

class RailroadAdmin(admin.ModelAdmin):
    exclude = ('cluster',)

admin.site.register(Ticket, TicketAdmin)
admin.site.register(TrainStation, TrainStationAdmin)
admin.site.register(Railroad, RailroadAdmin)
