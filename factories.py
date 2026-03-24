from interfaces import IView, IViewFactory, IDataService
from views_impl import (
    DashboardViewImpl,
    DatasetViewImpl,
    FindingsViewImpl,
    RecommendationsViewImpl,
    StatsViewImpl,
    ValidationViewImpl,
)

class StandardViewFactory(IViewFactory):
    """Concrete Factory implementing IViewFactory (Abstract Factory Pattern)."""
    def __init__(self, data_service: IDataService):
        self._data_service = data_service

    def create_dashboard(self, master) -> IView:
        return DashboardViewImpl(master, self._data_service)

    def create_dataset_view(self, master) -> IView:
        return DatasetViewImpl(master, self._data_service)

    def create_validation_view(self, master) -> IView:
        return ValidationViewImpl(master, self._data_service)

    def create_findings_view(self, master) -> IView:
        return FindingsViewImpl(master)

    def create_recommendations_view(self, master) -> IView:
        return RecommendationsViewImpl(master)

    def create_stats_view(self, master) -> IView:
        return StatsViewImpl(master)
