class DomainError(Exception):
    """Base class for all domain errors."""


class NotFoundError(DomainError):
    """Raised when an entity is not found."""

    def __init__(self, entity: str, identifier: object) -> None:
        super().__init__(f"{entity} não encontrado(a).")
        self.entity = entity
        self.identifier = identifier


class InvalidTransitionError(DomainError):
    """Raised when an invalid status transition is attempted."""


class ConcurrencyError(DomainError):
    """Raised when the record changed between reading and saving (another request won)."""


class CatalogUnavailableError(Exception):
    """O Catálogo não respondeu (não é erro de domínio: é falha de infraestrutura)."""
