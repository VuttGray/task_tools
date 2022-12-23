from task_tools.todoist_wrapper import TodoistWrapper, configure_todoist, get_label_by_duration

TOKEN = "MyToken"
DURATION_LABELS = {"5min": {"label": "5min", "minutes": 5},
                   "15min": {"label": "15min", "minutes": 15},
                   "30min": {"label": "30min", "minutes": 30},
                   "60min": {"label": "60min", "minutes": 60}}
configure_todoist(token=TOKEN, duration_labels=DURATION_LABELS)
TW = TodoistWrapper()
LABEL_SHALLOW = 'shallow'
LABEL_EMAIL_TODO = 'email_todo'


def test_get_label_by_duration():
    label = get_label_by_duration(5)
    assert label == "5min"


def test_add_task():
    task_id = ""
    task_name = f'Check email [01-Jan-2022 10:00 Daw, John Test email EML#105700000]'
    try:
        task_id = TW.add(content=task_name,
                         due='today',
                         labels=[get_label_by_duration(5), LABEL_SHALLOW, LABEL_EMAIL_TODO],
                         priority=2)
        assert task_id
        task = TW.get_task(task_id)
        assert task.raw_content == task_name
    finally:
        if task_id:
            TW.delete(task_id)
