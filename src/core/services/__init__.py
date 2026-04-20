"""Service classes decomposed from the DREAMSDatabase god class.

Each service owns a cohesive slice of behaviour (contacts, properties,
activities, pursuits, analytics, ...) and shares the underlying
connection with DREAMSDatabase. DREAMSDatabase keeps thin delegator
methods for backward compatibility while callers migrate to the
service interface directly.
"""

from src.core.services.contact_service import ContactService

__all__ = ["ContactService"]
