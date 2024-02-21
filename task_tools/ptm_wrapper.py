import datetime as dt
import logging
import requests
import json
from dateutil import parser as dt_parser
import urllib3

urllib3.disable_warnings()


class ItemTypes:
    Undefined = 0
    Coding = 1
    Testing = 2
    Review = 3
    Discussion = 4
    Meeting = 5
    Waiting = 6
    Assigning = 7
    Other = 8


ITEM_PRIORITIES = {
    'low': 0,
    'medium': 1,
    'high': 2,
    'critical': 3
}


class WrapperConfig:
    def __init__(self, **kwargs):
        self.api_url = kwargs.pop('api_url')
        self.user_login = kwargs.pop('user_login')


logger = logging.getLogger('logger')
conf: WrapperConfig


def configure_wrapper(**kwargs):
    global conf
    conf = WrapperConfig(**kwargs)


class PtmWrapperBaseException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class PtmApiBadRequestException(PtmWrapperBaseException):
    def __init__(self, response: requests.Response):
        self.status_code = response.status_code
        self.response_text = response.text
        self.message = f"Status code: {response.status_code}. Response: {response.text}"
        super().__init__(self.message)


class PtmValidationException(PtmWrapperBaseException):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class PtmApiNotResponseException(PtmWrapperBaseException):
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.message = f"Failed connection to {endpoint}"
        super().__init__(self.message)


class PtmProject:
    @property
    def id(self) -> id:
        return self.__id

    @property
    def name(self) -> str:
        return self.__name

    def __init__(self, src: dict):
        self.__id = src.get('id')
        self.__name = src.get('name')


class PtmItemTag:
    @property
    def item_id(self) -> int:
        return self.__item_id

    @property
    def tag_id(self) -> int:
        return self.__tag_id

    def __init__(self, item_id: int, tag_id: int):
        self.__item_id = item_id
        self.__tag_id = tag_id


class PtmTag:
    @property
    def id(self) -> int:
        return self.__id

    @property
    def name(self) -> str:
        return self.__name

    def __init__(self, src: dict):
        self.__id = src.get('id')
        self.__name = src.get('name')


class PtmItem:
    def __init__(self, src: dict):
        self.id = src.get('id')
        self.summary = src.get('summary')
        self.description = "" if src.get('description') is None else src.get('description')
        self.planned_date = dt_parser.parse(src.get('plannedDate')) if src.get('plannedDate') else None
        self.external_links = [link['externalEntryId'].lower() for link in src.get('externalLinks', [])]


class PtmWrapper:
    def __init__(self):
        logger.info('PTM wrapper created')

    def add(self, summary: str,
            duration: int,
            type_id: int,
            tags: list[str] = None,
            planned_date: (dt.datetime | dt.date | None) = None,
            priority: str = "medium",
            project: str = None,
            description: str = None,
            external_link: (str, str) = None) -> PtmItem:
        """
        Add task into PTM
        """
        project_id = self.find_project(project)
        priority_id = ITEM_PRIORITIES[priority.lower()] if priority.lower() in ITEM_PRIORITIES else 1
        item_tags = self.find_item_tags(0, tags)
        item = self.__create_item(summary=summary,
                                  duration=duration,
                                  type_id=type_id,
                                  item_tags=item_tags,
                                  planned_date=planned_date,
                                  priority_id=priority_id,
                                  project_id=project_id,
                                  description=description,
                                  external_link=external_link)
        logger.debug(f'PTM item {summary} created')
        return item

    def find_project(self, project_name: str) -> int:
        if project_name:
            project_id = 0
            for project in self.get_projects():
                if project.name.lower() == project_name.lower():
                    project_id = project.id
            if project_id is None or project_id <= 0:
                raise PtmValidationException(f'Project {project_name} not found')
            return project_id

    def find_tag(self, tag_name: str) -> int:
        tag_id = 0
        if tag_name:
            for tag in self.get_tags():
                if tag.name.lower() == tag_name.lower():
                    tag_id = tag.id
        if tag_name and (tag_id is None or tag_id <= 0):
            raise PtmValidationException(f'Tag {tag_name} not found')
        return tag_id

    def find_item_tags(self, item_id: int, tags: list[str]) -> list[PtmItemTag]:
        item_tags = []
        if tags:
            for tag in tags:
                item_tags.append(PtmItemTag(item_id, self.find_tag(tag)))
        return item_tags

    def search_items(self, search: str = None, date: dt.date = None):
        found_tasks = []
        items = self.get_items()
        for item in items:
            if (search is None
                or search.lower() in item.summary.lower()
                or search.lower() in item.external_links
                or search.lower() in item.description.lower())\
                    and (date is None or (item.planned_date and item.planned_date.date() == date)):
                found_tasks.append(item)
        return found_tasks

    def item_exists(self, search: str, date: dt.date = None):
        if self.search_items(search, date):
            return True

    @staticmethod
    def __create_item(summary: str,
                      duration: int,
                      type_id: int,
                      item_tags: list[PtmItemTag],
                      planned_date: (dt.datetime | dt.date | None) = None,
                      priority_id: int = 1,
                      project_id: int = None,
                      description: str = None,
                      start_date: dt.datetime = None,
                      due_date: dt.datetime = None,
                      closed_date: dt.datetime = None,
                      is_background: bool = False,
                      recurrence_string: str = None,
                      external_link: (str, str) = None) -> PtmItem:
        data = {
            'summary': summary,
            'description': description,
            'type': type_id,
            "plannedDate": planned_date.isoformat() if planned_date else None,
            'estimatedTime': duration,
            'tags': [{'tagId': it.tag_id} for it in item_tags],
            'priority': priority_id,
            'projectId': project_id,
            "startDate": start_date.isoformat() if start_date else None,
            "dueDate": due_date.isoformat() if due_date else None,
            "closedDate": closed_date.isoformat() if closed_date else None,
            'isBackground': is_background,
            "recurrenceString": recurrence_string,
            "externalLinks": [{"externalEntity": external_link[0], "externalEntryId": external_link[1]}],
        }
        endpoint = f"{conf.api_url}/Item/Create"
        request_json = json.dumps(data)
        response_json = PtmWrapper.api_post(endpoint, request_json)
        return PtmItem(response_json)

    @staticmethod
    def get_tags() -> list[PtmTag]:
        endpoint = f"{conf.api_url}/Tag/GetAll"
        response_json = PtmWrapper.api_get(endpoint)
        return [PtmTag(item) for item in response_json]

    @staticmethod
    def get_projects() -> list[PtmProject]:
        endpoint = f"{conf.api_url}/Project/GetAll"
        response_json = PtmWrapper.api_get(endpoint)
        return [PtmProject(item) for item in response_json]

    @staticmethod
    def get_items() -> list[PtmItem]:
        endpoint = f"{conf.api_url}/Item/GetOpen"
        response_json = PtmWrapper.api_get(endpoint)
        return [PtmItem(item) for item in response_json]

    @staticmethod
    def api_get(endpoint: str) -> json:
        try:
            response = requests.get(endpoint, verify=False)
        except requests.exceptions.ConnectionError as ex:
            logger.debug(ex)
            raise PtmApiNotResponseException(endpoint)
        if response.status_code == 200:
            return json.loads(response.text)

    @staticmethod
    def api_post(endpoint: str, request_json: json) -> json:
        headers = {'Content-Type': 'application/json', 'Accept': 'text/plain'}
        params = {'userLogin': conf.user_login}
        try:
            response = requests.post(endpoint, data=request_json, params=params, headers=headers, verify=False)
        except requests.exceptions.ConnectionError as ex:
            logger.debug(ex)
            raise PtmApiNotResponseException(endpoint)
        if response.status_code == 200:
            return json.loads(response.text)
        else:
            raise PtmApiBadRequestException(response)
