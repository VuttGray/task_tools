from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import truststore
import datetime as dt

truststore.inject_into_ssl()

class Changeset:
    def __init__(self, **kwargs):
        self.id = kwargs.pop("changeset_id")
        self.comment = kwargs.pop("comment")
        self.author = kwargs.pop("author").__dict__.get('display_name', 'Unknown')
        self.created_date = kwargs.pop("created_date")

    def __str__(self):
        return f"Changeset #{self.id}: comment '{self.comment}' by {self.author} at {self.created_date}"


class Project:
    def __init__(self, **kwargs):
        self.id = kwargs.pop("id")
        self.name = kwargs.pop("name")
        self.last_update_time = kwargs.pop("last_update_time")
        self.description = kwargs.pop("description")
        self.url = kwargs.pop("url")
        self.changesets: list[Changeset] = []
        self.commits_count = 0
        self.last_commit: dt.datetime

    def add_changeset(self, changeset: Changeset):
        self.changesets.append(changeset)

    def __str__(self):
        return f"{self.name}\t{self.url}"


def get_repos_activity(collection_url, pat):
    credentials = BasicAuthentication('', pat)
    connection = Connection(base_url=collection_url, creds=credentials)

    core_client = connection.clients.get_core_client()
    tfvc_client = connection.clients.get_tfvc_client()
    git_client = connection.clients.get_git_client()

    repos = []

    response = core_client.get_projects()
    if response:
        for p in response:
            tfvc_enabled = core_client.get_project_properties(p.id, ['System.SourceControlTfvcEnabled'])
            if tfvc_enabled and tfvc_enabled[0].value:
                changesets = tfvc_client.get_changesets(project=p.id)
                commits_count = len(changesets)
                last_commit = changesets[0].created_date if changesets else dt.datetime(2000, 1, 1)
                last_committer = changesets[0].checked_in_by.display_name if changesets else ''
                repos.append((p.name, commits_count, last_committer, last_commit))
            else:
                git_enabled = core_client.get_project_properties(p.id, ['System.SourceControlGitEnabled'])
                if git_enabled and git_enabled[0].value:
                    repos = git_client.get_repositories(p.id)
                    for rep in repos:
                        commits = git_client.get_commits(rep.id, None)
                        commits_count = len(commits)
                        last_commit = commits[0].committer.date if commits else dt.datetime(2000, 1, 1)
                        last_committer = commits[0].committer.name if commits else ''
                        repos.append((f"{p.name}: {rep.name}", commits_count, last_committer, last_commit))
