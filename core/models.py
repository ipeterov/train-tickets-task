import itertools
import json
import math

from django.db import models
from django.utils import timezone


class Ticket(models.Model):
	created_at = models.DateTimeField(auto_now_add=True)

	origin = models.ForeignKey('TrainStation', on_delete=models.SET_NULL, null=True, related_name='+')
	destination = models.ForeignKey('TrainStation', on_delete=models.SET_NULL, null=True, related_name='+')

	path = models.TextField()  # Список id станций в формате JSON

	enter_station = models.ForeignKey('TrainStation', on_delete=models.SET_NULL, null=True, related_name='+')
	entered_at = models.DateTimeField(null=True)

	exit_station = models.ForeignKey('TrainStation', on_delete=models.SET_NULL, null=True, related_name='+')
	exited_at = models.DateTimeField(null=True)

	price = models.DecimalField(max_digits=10, decimal_places=2)

	def __str__(self):
		return '{} - {} №{}'.format(self.origin, self.destination, self.id)

	@staticmethod
	def calculate_price(path):
		q = models.Q()
		for station1_id, station2_id in zip(path[:-1], path[1:]):
			q |= models.Q(station1_id=station1_id, station2_id=station2_id)
			q |= models.Q(station1_id=station2_id, station2_id=station1_id)

		rrs = Railroad.objects.filter(q)
		return rrs.aggregate(models.Sum('price'))['price__sum']

	@classmethod
	def create(cls, origin, destination):
		path = origin.shortest_path(destination)
		price = cls.calculate_price(path)
		return cls(origin=origin, destination=destination, path=json.dumps(path), price=price)

	def register_entry(self, station):
		if self.enter_station:
			raise Exception('Someone already entered with this ticket')

		if self.exit_station:
			raise Exception('Someone already entered and exited with this ticket')

		allowed_station_ids = json.loads(self.path)
		if station.id not in allowed_station_ids:
			raise Exception('Attempted entry at disallowed station')

		self.enter_station = station
		self.entered_at = timezone.now()
		self.save()

	def register_exit(self, station):
		if self.exit_station:
			raise Exception('Someone already entered and exited with this ticket')

		allowed_station_ids = json.loads(self.path)
		if station.id not in allowed_station_ids:
			raise Exception('Attempted exit at disallowed station')

		self.exit_station = station
		self.exited_at = timezone.now()
		self.save()


class TrainStation(models.Model):
	name = models.CharField(max_length=200)
	
	cluster = models.ForeignKey('Cluster', on_delete=models.CASCADE, related_name='stations')

	def possible_destinations(self):
		return TrainStation.objects.filter(cluster=self.cluster)

	def shortest_path(self, other_station):
		try:
			saved_path = SavedPath.objects.get(station1=self, station2=other_station)
		except SavedPath.DoesNotExist:
			pass
		else:
			return json.loads(saved_path.path)

		stations_by_id = {station.id: station for station in TrainStation.objects.prefetch_related('in_railroads', 'out_railroads')}
		railroads_by_id = {railroad.id: railroad for railroad in Railroad.objects.all()}

		unvisited_id_to_distance = {}
		prev = {}

		for station in stations_by_id.values():
			if station.id == self.id:
				unvisited_id_to_distance[station.id] = 0
			else:
				unvisited_id_to_distance[station.id] = math.inf

		while unvisited_id_to_distance:
			current_id, current_distance = min(unvisited_id_to_distance.items(), key=lambda x: x[1])
			del unvisited_id_to_distance[current_id]
			current = stations_by_id[current_id]

			if current_id == other_station.id:
				break

			for railroad in itertools.chain(current.in_railroads.all(), current.out_railroads.all()):
				neighbor_id = railroad.station1_id if railroad.station1_id != current.id else railroad.station2_id

				if neighbor_id in unvisited_id_to_distance and unvisited_id_to_distance[neighbor_id] > current_distance + railroad.length:
					unvisited_id_to_distance[neighbor_id] = current_distance + railroad.length
					prev[neighbor_id] = current_id

		path = []
		while current_id in prev:
			path.insert(0, current_id)
			current_id =  prev[current_id]

		path.insert(0, self.id)

		SavedPath.objects.create(station1=self, station2=other_station, path=json.dumps(path), cluster=self.cluster)

		return path

	def __str__(self):
		return self.name

	def clean(self):
		if not hasattr(self, 'cluster'):
			self.cluster = Cluster.objects.create()


class Railroad(models.Model):
	station1 = models.ForeignKey('TrainStation', on_delete=models.CASCADE, related_name='in_railroads')
	station2 = models.ForeignKey('TrainStation', on_delete=models.CASCADE, related_name='out_railroads')

	length = models.IntegerField()
	price = models.DecimalField(max_digits=10, decimal_places=2)

	cluster = models.ForeignKey('Cluster', on_delete=models.CASCADE, related_name='railroads')

	def __str__(self):
		return '{} - {}'.format(self.station1, self.station2)

	def clean(self):
		cluster1, cluster2 = self.station1.cluster, self.station2.cluster
		if cluster1 != cluster2:
			cluster2.stations.update(cluster=cluster1)
			cluster2.railroads.update(cluster=cluster1)
			cluster2.delete()
		self.cluster = cluster1
		SavedPath.objects.filter(cluster__in=(cluster1, cluster2)).delete()


class Cluster(models.Model):
	def __str__(self):
		return 'Cluster {}'.format(self.id)


class SavedPath(models.Model):
	station1 = models.ForeignKey('TrainStation', on_delete=models.CASCADE, related_name='+')
	station2 = models.ForeignKey('TrainStation', on_delete=models.CASCADE, related_name='+')

	cluster = models.ForeignKey('Cluster', on_delete=models.CASCADE, related_name='saved_paths')

	path = models.TextField()  # Список id станций в формате JSON