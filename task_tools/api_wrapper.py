import logging
import requests
import json
import urllib3

urllib3.disable_warnings()
logger = logging.getLogger('logger')


class ApiWrapperBaseException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class ApiBadRequestException(ApiWrapperBaseException):
    def __init__(self, response: requests.Response):
        self.status_code = response.status_code
        self.response_text = response.text
        self.message = f"Status code: {response.status_code}. Response: {response.text}"
        super().__init__(self.message)


class ApiNotResponseException(ApiWrapperBaseException):
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.message = f"Failed connection to {endpoint}"
        super().__init__(self.message)


def api_get(endpoint: str) -> json:
    try:
        response = requests.get(endpoint, verify=False)
    except requests.exceptions.ConnectionError as ex:
        logger.debug(ex)
        raise ApiNotResponseException(endpoint)

    if response.status_code == 200:
        return json.loads(response.text)
    else:
        raise ApiBadRequestException(response)


def api_post(endpoint: str, request_json: json, params: json) -> json:
    headers = {'Content-Type': 'application/json', 'Accept': 'text/plain'}

    try:
        response = requests.post(endpoint, data=request_json, params=params, headers=headers, verify=False)
    except requests.exceptions.ConnectionError as ex:
        logger.debug(ex)
        raise ApiNotResponseException(endpoint)
    if response.status_code in [200, 201]:
        return json.loads(response.text)
    else:
        raise ApiBadRequestException(response)
