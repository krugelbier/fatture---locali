# Base interface for invoice importers
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class InvoiceImportProvider(ABC):
    @abstractmethod
    def get_provider_name(self) -> str:
        """Restituisce il nome identificativo del provider di importazione"""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Testa lo stato di connessione o disponibilità del provider"""
        pass
