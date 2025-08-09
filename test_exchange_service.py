import pytest
import requests
from unittest.mock import patch, MagicMock
import json
import time
import os

# Add the root directory to the Python path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import exchange_service

# --- Provider Tests ---

@patch('requests.Session.get')
def test_boc_provider_success(mock_get):
    """Test BocProvider successful rate fetch."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"CNY": 0.115}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    provider = exchange_service.BocProvider()
    rate = provider.get_rate()

    assert rate == 0.115
    mock_get.assert_called_once_with("https://api.exchangerate-api.com/v4/latest/RUB", timeout=10)

@patch('requests.Session.get')
def test_boc_provider_failure(mock_get):
    """Test BocProvider handling a request failure."""
    mock_get.side_effect = requests.RequestException("API Error")

    provider = exchange_service.BocProvider()
    with pytest.raises(ValueError, match="第三方接口未返回卢布汇率"):
        provider.get_rate()

@patch('requests.Session.get')
def test_usd_provider_success(mock_get):
    """Test UsdProvider successful rate fetch."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"CNY": 7.25}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    provider = exchange_service.UsdProvider()
    rate = provider.get_rate()

    assert rate == 7.25
    mock_get.assert_called_once_with("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)

def test_fallback_provider():
    """Test the FallbackProvider."""
    provider = exchange_service.FallbackProvider(default=10.0)
    assert provider.get_rate() == 10.0

    provider_default = exchange_service.FallbackProvider()
    assert provider_default.get_rate() == 9.02

# --- Service Tests ---

# To test singletons properly, we need to reset them between tests
@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances before each test."""
    exchange_service.ExchangeRateService._instance = None
    exchange_service.UsdExchangeRateService._instance = None

@patch('threading.Thread')
@patch('exchange_service.BocProvider.get_rate', return_value=0.123)
@patch('builtins.open', side_effect=FileNotFoundError) # Mock file not found
def test_exchange_rate_service_api_success(mock_open, mock_get_rate, mock_thread):
    """Test service uses API when fallback file doesn't exist."""
    # The service will be initialized, fail to load from file,
    # and use the fallback provider's default initially.
    # The async refresh (which we've disabled) would normally fetch the new rate.
    # For this test, we can manually trigger the refresh logic or just check the state.
    service = exchange_service.ExchangeRateService()

    # Let's simulate the first async refresh call's effect manually
    service._rate = service._provider.get_rate()

    assert service.get_exchange_rate() == 0.123
    mock_get_rate.assert_called_once()


@patch('threading.Thread')
@patch('exchange_service.BocProvider.get_rate', side_effect=requests.RequestException)
@patch('builtins.open', side_effect=FileNotFoundError)
def test_exchange_rate_service_full_fallback(mock_open, mock_get_rate, mock_thread):
    """Test service falling back to default when API and file fail."""
    service = exchange_service.ExchangeRateService()
    # Should use FallbackProvider's default
    assert service.get_exchange_rate() == 9.02

@patch('threading.Thread')
@patch('exchange_service.BocProvider.get_rate')
def test_exchange_rate_service_loads_from_file(mock_get_rate, mock_thread):
    """Test that the service loads the rate from the fallback file."""
    fallback_data = {"rate": 0.150, "ts": time.time() - 1000}
    mock_file_content = json.dumps(fallback_data)

    with patch('builtins.open', MagicMock(read_data=mock_file_content)) as mock_open:
        # mock_open.return_value.__enter__.return_value.read.return_value = mock_file_content
        # This is complex, let's simplify by patching json.load
        with patch('json.load', return_value=fallback_data):
             service = exchange_service.ExchangeRateService()

    assert service.get_exchange_rate() == 0.150
    # API should not have been called as file is fresh enough for init
    mock_get_rate.assert_not_called()

def test_get_global_rates(mocker):
    """Test the global get_exchange_rate and get_usd_rate functions."""
    mocker.patch.object(exchange_service.ExchangeRateService, 'get_exchange_rate', return_value=10.0)
    mocker.patch.object(exchange_service.UsdExchangeRateService, 'get_exchange_rate', return_value=7.5)

    assert exchange_service.get_exchange_rate() == 10.0
    assert exchange_service.get_usd_rate() == 7.5
