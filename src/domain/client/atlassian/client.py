"""Atlassian facade: one import point for the Jira and Confluence clients."""
from domain.client.atlassian.confluence import ConfluenceClient
from domain.client.atlassian.http import AtlassianHttp
from domain.client.atlassian.jira import JiraClient

__all__ = ["AtlassianHttp", "ConfluenceClient", "JiraClient"]
