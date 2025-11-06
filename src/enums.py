"""
Enum base class for the consumer application.
Portfolio version: Base enum class.
"""
from enum import Enum


class BaseEnum(str, Enum):
    """Base enum class that extends both str and Enum."""
    def __str__(self) -> str:
        return str.__str__(self)

