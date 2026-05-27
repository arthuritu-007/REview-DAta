from core.interfaces import IDataService, IView, IViewFactory
from ui.views_impl import (
    DashboardViewImpl,
    DatasetViewImpl,
    FindingsViewImpl,
    RecommendationsViewImpl,
    StatsViewImpl,
    ValidationViewImpl,
)


class StandardViewFactory(IViewFactory):
    def __init__(self, data_service: IDataService):
        self._data_service = data_service

    def create_dashboard(self, master) -> IView:
        return DashboardViewImpl(master, self._data_service)

    def create_dataset_view(self, master) -> IView:
        return DatasetViewImpl(master, self._data_service)

    def create_validation_view(self, master) -> IView:
        return ValidationViewImpl(master, self._data_service)

    def create_findings_view(self, master) -> IView:
        return FindingsViewImpl(master, self._data_service)

    def create_recommendations_view(self, master) -> IView:
        return RecommendationsViewImpl(master, self._data_service)

    def create_stats_view(self, master) -> IView:
        return StatsViewImpl(master, self._data_service)

