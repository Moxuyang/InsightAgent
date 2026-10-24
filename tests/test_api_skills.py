import unittest
from unittest.mock import Mock, patch
import requests
from app.services.api_skill_executor import execute_api_skill, _format_api_result


class ApiSkillsTest(unittest.TestCase):
    def test_weather_table_keeps_time_units_and_zero(self):
        result = _format_api_result({'current': {'temperature_2m': 0, 'precipitation': 0, 'time': '2026-10-22T12:00'}, 'current_units': {'temperature_2m': '°C', 'precipitation': 'mm'}, 'latitude': 30.6, 'longitude': 104.1, 'timezone': 'Asia/Shanghai'})
        self.assertIn('| 气温 | 0 °C |', result)
        self.assertIn('2026-10-22T12:00', result)
        self.assertIn('天气模型', result)

    @patch('app.services.api_skill_executor.requests.get')
    def test_http_error_not_reported_as_success(self, get):
        response = Mock(status_code=503)
        get.return_value.raise_for_status.side_effect = requests.HTTPError('503 https://example.invalid?key=private-token', response=response)
        result = execute_api_skill({'api_url': 'https://example.invalid', 'api_method': 'GET'}, '天气')
        self.assertFalse(result['success'])
        self.assertIn('503', result['error'])
        self.assertNotIn('private-token', result['error'])

    def test_existing_general_result_is_preserved(self):
        self.assertEqual(_format_api_result({'data': 'hello'}), 'hello')


if __name__ == '__main__':
    unittest.main()
