from construction_management.construction_activity.activity import ConstructionActivity
from construction_management.construction_activity.bom_sync import sync_unloading_to_construction_bom


class Unloading(ConstructionActivity):
	stage = "Unloading"

	def on_update(self):
		if self.docstatus == 0:
			sync_unloading_to_construction_bom(self)

	def on_submit(self):
		sync_unloading_to_construction_bom(self)

	def on_cancel(self):
		super().on_cancel()
		sync_unloading_to_construction_bom(self, create_if_missing=False)
