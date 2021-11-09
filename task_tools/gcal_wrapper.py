import datetime as dt
from os import path
from logging import getLogger

from dateutil.parser import parse as dtu_parse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = getLogger('logger')

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']


class GCalConfig:
    def __init__(self, **kwargs):
        self.path_to_token = kwargs.pop('path_to_token', '..')
        self.token_file_name = kwargs.pop('token_file_name', 'token.json')
        self.token_path = path.join(self.path_to_token, self.token_file_name)
        self.credentials_path = kwargs.pop('credentials_path', path.join('..', 'credentials.json'))


conf: GCalConfig


def configure_gcal(**kwargs):
    global conf
    conf = GCalConfig(**kwargs)
    return conf


def get_credentials():
    credentials = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if path.exists(conf.token_path):
        credentials = Credentials.from_authorized_user_file(conf.token_path, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(conf.credentials_path, SCOPES)
            credentials = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(conf.token_path, 'w') as token:
            token.write(credentials.to_json())
    return credentials


def create_calendar_body(summary, description):
    return {
        "kind": "calendar#calendar",
        "description": description,
        "summary": summary,
        "timeZone": "Europe/Moscow"}


def create_event_body(summary, description, start, minutes, recurrence, task_id):
    end = (start + dt.timedelta(minutes=minutes))
    body = {"summary": summary,
            "start": {"dateTime": start.isoformat(),
                      "timeZone": "Europe/Moscow"},
            "end": {"dateTime": end.isoformat(),
                    "timeZone": "Europe/Moscow"},
            "extendedProperties": {"private": {"task_id": task_id}}
            }
    if summary != description:
        body["description"] = description
    if recurrence:
        body["recurrence"] = [recurrence]
    return body


class GoogleCalEvent:
    def __init__(self, event):
        self.start_date = dtu_parse(event['start'].get('dateTime', event['start'].get('date')))
        self.end_date = dtu_parse(event['end'].get('dateTime', event['end'].get('date')))
        self.duration = int((self.end_date - self.start_date).seconds / 60)
        self.summary = event.get('summary')
        self.description = event.get('description')
        if 'extendedProperties' in event and 'private' in event['extendedProperties']:
            self.task_id = int(event['extendedProperties']['private'].get('task_id'))
        else:
            self.task_id = None


class GoogleCalWrapper:
    def __init__(self):
        credentials = get_credentials()
        self.__service = build('calendar', 'v3', credentials=credentials)
        self.__active_cal_id = None
        self.events = {}
        logger.info('GCal wrapper created')

    def __get_calendar_id(self, summary):
        calendars_result = self.__service.calendarList().list().execute()
        calendars = calendars_result.get('items', [])
        for calendar in calendars:
            if summary == calendar['summary']:
                return calendar['id']

    def load_events(self):
        time_min = (dt.datetime.utcnow() - dt.timedelta(days=7)).isoformat() + 'Z'  # 'Z' indicates UTC time
        time_max = (dt.datetime.utcnow() + dt.timedelta(days=60)).isoformat() + 'Z'  # 'Z' indicates UTC time
        events_result = self.__service.events().list(calendarId=self.__active_cal_id,
                                                     timeMin=time_min,
                                                     timeMax=time_max,
                                                     singleEvents=True,
                                                     orderBy='startTime').execute()
        self.events = [GoogleCalEvent(e) for e in events_result.get('items', [])]
        return self.events

    def create_calendar(self, calendar_name, calendar_description):
        body = create_calendar_body(calendar_name, calendar_description)
        result = self.__service.calendars().insert(body=body).execute()
        self.set_active_calendar(calendar_id=result['id'])
        return result

    def set_active_calendar(self, calendar_id=None, calendar_name=None):
        if calendar_id:
            self.__active_cal_id = calendar_id
        elif calendar_name:
            self.__active_cal_id = self.__get_calendar_id(calendar_name)
        else:
            self.__active_cal_id = None
        return self.__active_cal_id

    def print_calendars(self):
        print('------Calendars---------')
        calendars_result = self.__service.calendarList().list().execute()
        calendars = calendars_result.get('items', [])

        if not calendars:
            print('No calendars found.')
        for calendar in calendars:
            summary = calendar['summary']
            cal_id = calendar['id']
            primary = "Primary" if calendar.get('primary') else ""
            print("%s\t%s\t%s" % (summary, cal_id, primary))

    def get_upcoming_events(self):
        now = dt.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        events_result = self.__service.events().list(calendarId=self.__active_cal_id,
                                                     timeMin=now,
                                                     maxResults=100,
                                                     singleEvents=True,
                                                     orderBy='startTime').execute()
        return [GoogleCalEvent(e) for e in events_result.get('items', [])]

    def search_event(self, time_min=None, time_max=None, private_extended_property=None):
        events_result = self.__service.events().list(calendarId=self.__active_cal_id,
                                                     timeMin=time_min,
                                                     timeMax=time_max,
                                                     privateExtendedProperty=private_extended_property,
                                                     maxResults=100,
                                                     singleEvents=True,
                                                     orderBy='startTime').execute()
        events = events_result.get('items', [])
        if len(events) > 1:
            raise UserWarning('More than one calendar event found for one task')
        elif len(events) == 1:
            return GoogleCalEvent(events[0])

    def print_events(self):
        print('------Upcoming events----')
        events = self.get_upcoming_events()

        if not events:
            print('No upcoming events found.')
        for event in events:
            print(event.start_date, event.summary)

    def set_event(self, event_id, summary, description, start, minutes, recurrence, task_id):
        body = create_event_body(summary, description, start, minutes, recurrence, task_id)
        if event_id:
            self.__service.events().update(calendarId=self.__active_cal_id, eventId=event_id, body=body).execute()
        else:
            self.__service.events().insert(calendarId=self.__active_cal_id, body=body).execute()

    def clear_events(self):
        events_result = self.__service.events().list(calendarId=self.__active_cal_id,
                                                     singleEvents=True,
                                                     orderBy='startTime').execute()
        for e in events_result.get('items', []):
            self.__service.events().delete(calendarId=self.__active_cal_id,
                                           eventId=e['id']).execute()
