"""
Pytest configuration and fixtures for tests.
"""
import pytest

from src.utils.payload import parse_to_payload


def parse_json_to_payload(json_str: str):
    """Helper function to parse JSON string to payload dictionary."""
    return parse_to_payload(json_str)

