from enum import Enum, auto
from logging import getLogger
from re import findall

import requests
import requests.packages.urllib3
from dateutil.parser import parse as dtu_parse
from jira import JIRA, Issue, JIRAError  # Documentation: https://jira.readthedocs.io/en/master/api.html#jira
from requests.auth import HTTPBasicAuth

requests.packages.urllib3.disable_warnings()
logger = getLogger('logger')


class IssueStatus(Enum):
    IN_PROGRESS = auto()
    ACCEPTED = auto()
    UAT = auto()
    ON_HOLD = auto()
    PLANNED = auto()
    PENDING = auto()
    WAITING_SUPPORT = auto()
    TODO = auto()


class JiraIssueNotFound(JIRAError):
    pass


class JiraUnavailable(JIRAError):
    pass


class JiraConfig:
    def __init__(self, **kwargs):
        self.jira_server = kwargs.pop('jira_server')
        if len(self.jira_server) == 0:
            raise ValueError("Jira server is not specified for jira wrapper")
        self.ssl_cert_path = kwargs.pop('ssl_cert_path')
        if len(self.ssl_cert_path) == 0:
            raise ValueError("Path to SSL certificate is not specified for jira wrapper")
        self.login = kwargs.pop('login')
        if len(self.login) == 0:
            raise ValueError("Login is not specified for jira wrapper")
        self.password = kwargs.pop('password')
        if len(self.password) == 0:
            raise ValueError("Password is not specified for jira wrapper")


conf: JiraConfig


def configure_jira(**kwargs):
    global conf
    conf = JiraConfig(**kwargs)
    return conf


def find_jira_keys(text):
    results = findall(r'(\[|browse/)*(DR-\d+|SR-\d+)(])*', text)
    for key in [r[1] for r in results if r[0] == '' and r[2] == '']:
        yield key


def get_issue_link(key) -> str:
    return f'{conf.jira_server}/browse/{key}'


def check_service():
    try:
        r = requests.get(conf.jira_server,
                         verify=conf.ssl_cert_path,
                         timeout=1)
        if r.status_code == 401:
            r = requests.get(conf.jira_server,
                             verify=conf.ssl_cert_path,
                             auth=HTTPBasicAuth(conf.login, conf.password))
        r.raise_for_status()
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as ex:
        logger.exception(ex)
        raise JiraUnavailable


class JiraIssue:
    CLOSURE_STATUSES = ['Closed', 'Fixed', 'Resolved', 'Canceled', 'Rejected', 'Declassified']

    @property
    def is_closed(self):
        return self.status in self.CLOSURE_STATUSES

    def __init__(self, issue: Issue):
        self.key = issue.key
        self.reporter = issue.fields.reporter.displayName
        self.team_id = issue.fields.customfield_10600.id if issue.fields.customfield_10600 else None
        self.closed_date = dtu_parse(issue.fields.resolutiondate) if issue.fields.resolutiondate else None
        self.status = issue.fields.status.name


class JiraWrapper:
    def __init__(self):
        check_service()
        self.__jira = JIRA(options={'server': conf.jira_server, 'verify': conf.ssl_cert_path},
                           basic_auth=(conf.login, conf.password))
        logger.info('Jira wrapper created')

    def get_issue(self, issue_key) -> Issue:
        try:
            return self.__jira.issue(issue_key)
        except JIRAError as ex:
            if ex.text == "Issue Does Not Exist":
                raise JiraIssueNotFound(issue_key)

    def find_by_filter(self, search_filter):
        issues = {}
        for issue in self.__jira.search_issues("filter=" + search_filter):
            issues[issue.key] = issue
        return issues

    def find_version(self, project, name):
        for v in self.__jira.project_versions(project):
            if v.name.upper() == name.upper():
                return v

    def archive_versions(self, project, archive_date):
        for v in self.__jira.project_versions(project):
            release_date = dtu_parse(v.releaseDate)
            if v.released and not v.archived and release_date.date() <= archive_date:
                v.update(archived=True)

    def release_version(self, project, version_name, released_date):
        version = self.find_version(project, version_name)
        if version:
            version.update(releaseDate=released_date.strftime('%Y-%m-%d'), released=True)
            logger.info(f'Released Jira version {version_name}')

    def create_new_version(self, project, name, start_date, release_date, description=None):
        logger.debug(f'JW: Jira version {name} creation')
        self.__jira.create_version(project=project,
                                   name=name,
                                   startDate=start_date.strftime('%Y-%m-%d'),
                                   releaseDate=release_date.strftime('%Y-%m-%d'),
                                   description=description)
        logger.info(f'Jira version {name} created')

    def get_unreleased_versions(self, project):
        return [v.name for v in self.__jira.project_versions(project) if not v.released and not v.archived]
