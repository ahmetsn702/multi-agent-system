"""
Unit tests for the _is_api_project helper method.
"""
import pytest
from core.orchestrator import Orchestrator


class TestIsApiProjectHelper:
    """Test the _is_api_project static helper method."""

    def test_detects_fastapi_keyword(self):
        """Test that 'fastapi' keyword is detected."""
        assert Orchestrator._is_api_project("Create a FastAPI application")
        assert Orchestrator._is_api_project("Build a fastapi service")

    def test_detects_api_keyword(self):
        """Test that 'api' keyword is detected."""
        assert Orchestrator._is_api_project("Create an API for users")
        assert Orchestrator._is_api_project("Build a REST API")

    def test_detects_web_keyword(self):
        """Test that 'web' keyword is detected."""
        assert Orchestrator._is_api_project("Create a web service")
        assert Orchestrator._is_api_project("Build a web application")

    def test_detects_rest_keyword(self):
        """Test that 'rest' keyword is detected."""
        assert Orchestrator._is_api_project("Create a REST service")
        assert Orchestrator._is_api_project("Build a RESTful API")

    def test_detects_backend_keyword(self):
        """Test that 'backend' keyword is detected."""
        assert Orchestrator._is_api_project("Create a backend service")
        assert Orchestrator._is_api_project("Build a backend application")

    def test_case_insensitive(self):
        """Test that detection is case-insensitive."""
        assert Orchestrator._is_api_project("Create a FASTAPI application")
        assert Orchestrator._is_api_project("Build an API")
        assert Orchestrator._is_api_project("Create a WEB service")

    def test_non_api_projects(self):
        """Test that non-API projects are not detected."""
        assert not Orchestrator._is_api_project("Create a CLI tool")
        assert not Orchestrator._is_api_project("Build a data analysis script")
        assert not Orchestrator._is_api_project("Generate a report")
        assert not Orchestrator._is_api_project("Process some files")

    def test_empty_string(self):
        """Test that empty string returns False."""
        assert not Orchestrator._is_api_project("")

    def test_partial_matches_not_detected(self):
        """Test that partial keyword matches don't trigger false positives."""
        # These should NOT be detected as API projects
        assert not Orchestrator._is_api_project("Create a paper document")
        assert not Orchestrator._is_api_project("Build a desktop application")
        # Note: "website" contains "web" keyword, so it WILL be detected as API project
        # This is intentional behavior since websites often need backend APIs
