"""Source adapters: translate each external source into a CallEnvelope."""

from ingestion.adapters.base import SourceAdapter
from ingestion.adapters.folder import FolderAdapter
from ingestion.adapters.mock_crm import MockCrmAdapter
from ingestion.adapters.rest import RestAdapter

__all__ = ["SourceAdapter", "FolderAdapter", "RestAdapter", "MockCrmAdapter"]
