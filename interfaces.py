from abc import ABC, abstractmethod
import customtkinter as ctk

class IView(ABC):
    """Interface for all Views in the application."""
    @abstractmethod
    def get_frame(self) -> ctk.CTkFrame:
        pass

class IViewFactory(ABC):
    """Abstract Factory for creating Views."""
    @abstractmethod
    def create_dashboard(self, master) -> IView:
        pass

    @abstractmethod
    def create_dataset_view(self, master) -> IView:
        pass

    @abstractmethod
    def create_validation_view(self, master) -> IView:
        pass

    @abstractmethod
    def create_findings_view(self, master) -> IView:
        pass

    @abstractmethod
    def create_recommendations_view(self, master) -> IView:
        pass

    @abstractmethod
    def create_stats_view(self, master) -> IView:
        pass

class IDataService(ABC):
    """Interface for data operations (Single Responsibility)."""
    @abstractmethod
    def get_all_datasets(self) -> list:
        pass

    @abstractmethod
    def add_dataset(self, name: str, file_type: str, records: int) -> dict:
        pass
