import datetime as dt
import re
from dataclasses import dataclass
from logging import getLogger
from typing import Union

from dateutil.parser import parse as dtu_parse
from todoist_api_python.api import TodoistAPI

# Todoist API documentations
# https://developer.todoist.com/rest/v2#overview
# https://pypi.org/project/todoist-api-python/
# https://github.com/Doist/todoist-api-python


@dataclass(order=True)
class DurationLabel:
    label: str
    minutes: int

    def __post_init__(self):
        self.sort_index = self.minutes


class TodoistConfig:
    def __init__(self, **kwargs):
        self.token = kwargs.pop('token')
        if len(self.token) == 0:
            raise ValueError("Token is not specified for todoist wrapper")
        dl = kwargs.pop('duration_labels', {})
        if dl:
            self.duration_labels = {key: DurationLabel(**value) for key, value in dl.items()}


logger = getLogger('logger')
conf: TodoistConfig


def configure_todoist(**kwargs):
    global conf
    conf = TodoistConfig(**kwargs)


def get_label_by_duration(minutes):
    labels = [lbl.label for lbl in conf.duration_labels.values() if lbl.minutes == minutes]
    return labels[0] if labels else None


def get_todoist_link(text, url):
    return f'[{text}]({url})'


class TodoistWrapper:
    def __init__(self):
        self.__api = TodoistAPI(conf.token)
        self.projects = self.get_projects()
        self.labels = self.get_labels()
        logger.info('Todoist wrapper created')

    # def sync(self):
    #     logger.info('Todoist sync')
    #     self.__api.sync()

    def add(self, content, due, labels, project=None, priority=None) -> str:
        """
        Add task into Todoist
        """
        if labels is None:
            labels = []
        # else:
        #     labels = self.find_labels(labels)
        project_id = self.find_project(project)
        if project and project_id is None:
            raise UserWarning(f'Project {project} not found')
        task = self.__api.add_task(content,
                                   due={'string': due},
                                   project_id=project_id,
                                   labels=labels,
                                   priority=priority,
                                   description='')
        logger.debug(f'Todoist task {content} created')
        return task.id

    def delete(self, task_id: str):
        self.__api.delete_task(task_id)

    def find_project(self, project_name: str) -> str:
        if project_name is None:
            return self.find_project('Inbox')
        for project in self.projects.values():
            if project.name.lower() == project_name.lower():
                return project.id

    # def find_labels(self, labels: list[str]) -> []:
    #     found_labels = []
    #     labels = [label.lower() for label in labels]
    #     for label in self.labels.values():
    #         if label.name.lower() in labels:
    #             found_labels.append(label.id)
    #     return found_labels

    def search_projects(self, search: str) -> []:
        found_projects = []
        for p in self.projects.values():
            if search in p.name:
                found_projects.append(p.data)
        return found_projects

    def get_task(self, task_id: str):
        task = self.__api.get_task(task_id)
        return TodoistTask(task, self)

    def get_tasks(self):
        return [TodoistTask(i, self) for i in self.__api.get_tasks()]

    def get_projects(self) -> {}:
        return {p.id: TodoistProject(p) for p in self.__api.get_projects()}

    def get_labels(self) -> {}:
        return {lbl.id: TodoistLabel(lbl) for lbl in self.__api.get_labels()}

    def get_open_tasks(self) -> []:
        return [TodoistTask(i, self) for i in self.__api.get_tasks()]

    def get_closed_tasks(self, date_from: Union[dt.date, dt.datetime] = dt.date.today()) -> []:
        raise NotImplementedError

    def search_tasks(self, search: str = None, date: dt.date = None):
        found_tasks = []
        tasks = self.get_open_tasks()
        for task in tasks:
            if (search is None or search in task.raw_content)\
                    and (date is None or task.date.date() == date):
                found_tasks.append(task)
        return found_tasks

    def task_exists(self, search: str, date: dt.date = None):
        if self.search_tasks(search, date):
            return True

    def set_content(self, item_id: str, content: str):
        self.__api.update_task(task_id=item_id, content=content)


class TodoistLabel:
    def __init__(self, label, is_deleted: bool = False):
        self.id = label.id
        self.is_deleted = is_deleted
        self.name = label.name

    def __repr__(self):
        return self.name


class TodoistProject:
    def __init__(self, project, is_archived: bool = False, is_deleted: bool = False):
        self.id = project.id
        self.name = project.name
        self.parent_id = project.parent_id
        self.is_archived = is_archived
        self.is_deleted = is_deleted

    def __repr__(self):
        return self.name


class TodoistTask:
    @property
    def summary(self):
        return self.pure_content[:50]

    @property
    def pure_content(self) -> str:
        return self.__pure_content

    @property
    def duration(self) -> int:
        return self.__duration

    @property
    def raw_content(self):
        return self.__raw_content

    @raw_content.setter
    def raw_content(self, val):
        self.__raw_content = val
        content = self.parse_short_duration(val)
        content = self.parse_time_period(content)
        content = self.parse_links(content)
        self.__pure_content = content
        self.__duration = self.get_duration()

    @property
    def is_open(self):
        return not self.is_closed

    @property
    def has_time(self):
        return self.date and self.date.hour > 0

    def __init__(self, task: {}, tw: TodoistWrapper):
        self.id = task.id
        self.__pure_content = task.content

        self.is_closed = task.is_completed
        # self.closed_date = not supported in v.2
        self.created_date = dtu_parse(task.created_at) if task.created_at else None
        self.is_recurring = task.due.is_recurring if task.due else None
        self.date = dtu_parse(task.due.date) if task.due and task.due.date else None
        label_ids = task.labels if task.labels else []
        self.labels = [tw.labels.get(lid) for lid in label_ids]
        self.project = tw.projects.get(task.project_id)

        # parse content
        self.__pure_content = self.__duration = self.__short_duration = self.__start_time = self.__end_time = None
        self.__links = []
        self.raw_content = task.content

    def __repr__(self):
        return self.pure_content

    def get_duration(self) -> int:
        # cross join task labels and duration labels dictionary to get only duration labels for the task
        duration_labels = set([lbl.id for lbl in self.labels if lbl]) & set(conf.duration_labels.keys())
        if duration_labels:
            return max([conf.duration_labels[lid].minutes for lid in duration_labels])
        return 0

    def process_links(self, links: {}):
        content = self.raw_content
        for key, url in links.items():
            content = re.sub(key, get_todoist_link(key, url), content)
        self.raw_content = content

    def parse_short_duration(self, content: str) -> str:
        d = re.findall(r'^\((\d+\+?)\)', content)
        self.__short_duration = None
        if d:
            self.__short_duration = d[0]
            d = d[0].replace("+", r"\+")
            content = re.sub(fr'^\({d}\)', '', content)
        return content.strip()

    def parse_time_period(self, content: str) -> str:
        result = re.findall(r'\d{1,2}:\d{2}-\d{1,2}:\d{2}', content)
        if result:
            time1_str, time2_str = result[0].split('-')
            self.__start_time = dt.datetime.strptime(time1_str, '%H:%M').time()
            self.__end_time = dt.datetime.strptime(time2_str, '%H:%M').time()
            content = content.replace(result[0], '')
        return content.strip()

    def parse_links(self, content):
        self.__links = re.findall(r'\[([^]]+)]\((http[s]*://[^)]+)\)', content)
        for t, l in self.__links:
            content = content.replace(f'[{t}]({l})', t)
        return content.strip()

    def get_content(self):
        content = self.pure_content
        for t, l in self.__links:
            content = content.replace(t, f'[{t}]({l})')
        return content

    def check_label(self, label):
        return label.lower() in [lbl.name.lower() for lbl in self.labels]
