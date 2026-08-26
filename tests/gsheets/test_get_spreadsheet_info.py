"""Tests for spreadsheet metadata needed by read-only indexers."""

from unittest.mock import Mock

import pytest

from gsheets.sheets_tools import get_spreadsheet_info


@pytest.mark.asyncio
async def test_get_spreadsheet_info_exposes_non_grid_sheet_types():
    service = Mock()
    service.spreadsheets().get().execute = Mock(
        return_value={
            "properties": {"title": "Connected data", "locale": "en_GB"},
            "sheets": [
                {
                    "properties": {
                        "title": "Connected sheet 1",
                        "sheetId": 7,
                        "sheetType": "DATA_SOURCE",
                        "gridProperties": {"rowCount": 500, "columnCount": 20},
                    },
                    "conditionalFormats": [],
                },
                {
                    "properties": {
                        "title": "Sheet1",
                        "sheetId": 0,
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 1000, "columnCount": 26},
                    },
                    "conditionalFormats": [],
                },
            ],
        }
    )
    impl = get_spreadsheet_info.__wrapped__.__wrapped__

    result = await impl(
        service=service,
        user_google_email="user@example.com",
        spreadsheet_id="spreadsheet-123",
    )

    assert '"Connected sheet 1" (ID: 7) | Type: DATA_SOURCE | Size: 500x20' in result
    assert '"Sheet1" (ID: 0) | Type: GRID | Size: 1000x26' in result
