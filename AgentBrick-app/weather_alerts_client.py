"""
Client for the National Weather Service (NWS) Weather Alerts API.

Fetches active weather alerts for all US states and normalizes them for storage
in Lakebase (Databricks-managed Postgres).

API Reference: https://www.weather.gov/documentation/services-web-api
No API key required - this is a public government API.
"""

import hashlib
import json
from datetime import datetime
from typing import Any

import requests

# All US state 2-letter codes
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP"  # territories
]

_BASE_URL = "https://api.weather.gov"
_DEFAULT_TIMEOUT = 30


class WeatherAlertsClient:
    """Client for fetching weather alerts from the National Weather Service API."""

    def __init__(self, base_url: str | None = None, timeout: int = _DEFAULT_TIMEOUT):
        self.base_url = (base_url or _BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        # NWS API requires a User-Agent header
        self._session.headers.update(
            {
                "User-Agent": "(Databricks Weather App, contact@databricks.com)",
                "Accept": "application/geo+json",
            }
        )

    def get_alerts_for_state(self, state_code: str) -> dict[str, Any]:
        """
        Fetch active weather alerts for a specific state.
        
        Args:
            state_code: 2-letter state code (e.g., "CA", "NY")
            
        Returns:
            Raw API response with GeoJSON features array
        """
        url = f"{self.base_url}/alerts/active/area/{state_code.upper()}"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_all_alerts(self) -> list[dict[str, Any]]:
        """
        Fetch active weather alerts for all US states and territories.
        
        Returns:
            List of normalized alert dictionaries ready for database storage
        """
        all_alerts = []
        
        for state_code in US_STATES:
            try:
                print(f"Fetching alerts for {state_code}...")
                raw_data = self.get_alerts_for_state(state_code)
                
                # Extract features (alerts) from the GeoJSON response
                features = raw_data.get("features", [])
                
                for feature in features:
                    normalized = self._normalize_alert(feature, state_code)
                    if normalized:
                        all_alerts.append(normalized)
                        
            except requests.HTTPError as e:
                print(f"Error fetching alerts for {state_code}: {e}")
                continue
            except Exception as e:
                print(f"Unexpected error for {state_code}: {e}")
                continue
        
        return all_alerts

    def _normalize_alert(self, feature: dict[str, Any], state_code: str) -> dict[str, Any] | None:
        """
        Normalize a raw NWS alert feature into our database schema.
        
        Schema:
            - id: stable dedup key (alert ID from NWS)
            - location: city/state or area description
            - source_type: "alert"
            - headline: alert headline
            - event: event type (e.g., "Flash Flood Warning")
            - narrative_text: description + instruction combined
            - issued_at: when the alert was issued
            - effective_at: when the alert becomes effective
            - expires_at: when the alert expires
            - payload: raw JSON for provenance
            - synced_at: timestamp when we fetched it
        """
        try:
            properties = feature.get("properties", {})
            
            # Extract required fields
            alert_id = properties.get("id")
            if not alert_id:
                return None
            
            # Location: use areaDesc ("Los Angeles County; Ventura County")
            area_desc = properties.get("areaDesc", "")
            location = f"{area_desc}, {state_code}" if area_desc else state_code
            
            # Event and headline
            event = properties.get("event", "Unknown")
            headline = properties.get("headline", "")
            
            # Narrative text: combine description and instruction
            description = properties.get("description", "")
            instruction = properties.get("instruction", "")
            narrative_parts = []
            if description:
                narrative_parts.append(description)
            if instruction:
                narrative_parts.append(f"INSTRUCTIONS: {instruction}")
            narrative_text = "\n\n".join(narrative_parts)
            
            # Timestamps
            issued_at = self._parse_timestamp(properties.get("sent"))
            effective_at = self._parse_timestamp(properties.get("effective"))
            expires_at = self._parse_timestamp(properties.get("expires"))
            
            # Current sync time
            synced_at = datetime.utcnow()
            
            return {
                "id": alert_id,
                "location": location,
                "source_type": "alert",
                "headline": headline,
                "event": event,
                "narrative_text": narrative_text,
                "issued_at": issued_at,
                "effective_at": effective_at,
                "expires_at": expires_at,
                "payload": json.dumps(feature),  # Store raw feature as JSON
                "synced_at": synced_at,
            }
        except Exception as e:
            print(f"Error normalizing alert: {e}")
            return None

    @staticmethod
    def _parse_timestamp(ts_str: str | None) -> datetime | None:
        """Parse ISO 8601 timestamp string to datetime object."""
        if not ts_str:
            return None
        try:
            # NWS uses ISO 8601 format: "2024-01-15T10:30:00-08:00"
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            return None