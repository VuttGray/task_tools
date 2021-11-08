from datetime import date, datetime, timedelta
from logging import getLogger

from dateutil.parser import parse as dtu_parse
from toggl.TogglPy import Toggl  # TogglPy: https://github.com/matthewdowney/TogglPy

logger = getLogger('logger')


class TogglConfig:
    def __init__(self, **kwargs):
        self.token = kwargs.pop('token')
        if len(self.token) == 0:
            raise ValueError("Toggl token is not specified for toggl wrapper")
        self.workspace_id = kwargs.pop('workspace_id')
        if not isinstance(self.workspace_id, int):
            raise ValueError("Toggl workspace for toggl wrapper has not correct type")


conf: TogglConfig


def configure_toggl(**kwargs):
    global conf
    conf = TogglConfig(**kwargs)
    return conf


class TimeEntry:
    def __init__(self, data):
        self.id = self.start = self.end = self.project = self.description = ''
        self.tags = []
        self.__dict__ = data
        self.start_date = dtu_parse(self.start)
        self.end_date = dtu_parse(self.end)
        self.minutes = round((self.start_date - self.end_date).seconds / 60) if self.start_date and self.end_date else 0

    def get_unified_description(self):
        return self.description

    def __repr__(self):
        return f'{self.project:25} | {self.minutes:4.2f} | {self.description} ({", ".join(self.tags)})'


class TogglWrapper:
    def __init__(self):
        self.__t = Toggl()
        self.__t.setAPIKey(conf.token)
        self.__time_entries = []
        self.__sync_date = None
        logger.info('Toggl wrapper created')

    def __load_detailed_report(self, start_date: date, end_date: date):
        data = {
            'workspace_id': conf.workspace_id,
            'since': start_date.strftime('%Y-%m-%d'),
            'until': end_date.strftime('%Y-%m-%d'),
        }
        det_rep = self.__t.getDetailedReport(data)
        self.__sync_date = datetime.now()
        return det_rep

    def get_time_tracker(self, start_date: date = None, end_date: date = None, return_class=TimeEntry):
        if self.__sync_date is None or self.__sync_date + timedelta(seconds=300) < datetime.now():
            start_date = start_date if start_date else date.today()
            end_date = end_date if end_date and end_date >= start_date else start_date
            det_rep = self.__load_detailed_report(start_date, end_date)
            self.__time_entries = [return_class(t) for t in det_rep['data']]
        return self.__time_entries

    def update_time_entry(self, time_entry_id: int, updated_parameters: dict):
        if 'id' not in updated_parameters:
            updated_parameters.update({'id': time_entry_id})
        self.__t.putTimeEntry(parameters=updated_parameters)
