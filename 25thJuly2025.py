import requests
import base64
import os
import csv
import re
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables from .env
load_dotenv()

# Jira credentials from environment
JIRA_DOMAIN = os.getenv('JIRA_DOMAIN')
JIRA_EMAIL = os.getenv('JIRA_EMAIL')
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')

# Encode Jira API credentials
auth_string = f'{JIRA_EMAIL}:{JIRA_API_TOKEN}'.encode('utf-8')
AUTH = base64.b64encode(auth_string).decode('utf-8')

# API headers
HEADERS = {
    'Authorization': f'Basic {AUTH}',
    'Accept': 'application/json'
}

# Output CSV folder
CSV_OUTPUT_FOLDER = '25thJulyReports'
os.makedirs(CSV_OUTPUT_FOLDER, exist_ok=True)

# --------------------------- Utility Functions --------------------------- #

def get_projects():
    """Fetch all Jira projects."""
    url = f'https://{JIRA_DOMAIN}/rest/api/3/project/search'
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return [{'key': p['key'], 'name': p['name']} for p in data.get('values', [])]



def parse_jira_date(date_str):
    """Convert Jira datetime string to naive Python datetime."""
    if not date_str:
        return None
    try:
        if 'T' in date_str:
            if date_str.endswith('Z'):
                dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%fZ')
            elif '+' in date_str or date_str.count(':') > 2:
                dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f%z')
                return dt.replace(tzinfo=None)  # strip timezone
            else:
                dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
        else:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt
    except ValueError as e:
        print(f"Error parsing date '{date_str}': {e}")
        return None

def format_date(date_str):
    """Convert Jira date to YYYY-MM-DD string."""
    parsed_date = parse_jira_date(date_str)
    return parsed_date.date().isoformat() if parsed_date else ''

def remove_emojis(text):
    """Remove emojis and non-ASCII characters."""
    if not text:
        return ''
    text = re.sub(
        "[" 
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002700-\U000027BF"
        "\U0001F900-\U0001F9FF"
        "\U00002600-\U000026FF"
        "]+", '', text, flags=re.UNICODE
    )
    return ''.join(char for char in text if ord(char) < 128)

def compute_metrics(task, raw_created, raw_resolved, raw_due):
    """Compute time to resolve and SLA metrics."""
    try:
        created = parse_jira_date(raw_created)
        resolved = parse_jira_date(raw_resolved)
        due = parse_jira_date(raw_due)

        task['time_to_resolve_days'] = (resolved - created).days if resolved and created else ''
        task['delay_days'] = (resolved - due).days if resolved and due else ''
        task['sla_met'] = 'Yes' if resolved and due and resolved <= due else 'No' if resolved and due else 'N/A'
    except Exception as e:
        print(f"Error computing metrics: {e}")
        task['time_to_resolve_days'] = ''
        task['delay_days'] = ''
        task['sla_met'] = 'N/A'

# --------------------------- Main Issue Extraction --------------------------- #

def get_project_issues(project_key, project_name):
    """Fetch issues for a specific project and return formatted rows."""
    url = f'https://{JIRA_DOMAIN}/rest/api/3/search'
    start_at = 0
    max_results = 100
    all_issues = []

    while True:
        params = {
            'jql': f'project={project_key}',
            'fields': 'assignee,summary,status,created,duedate,resolutiondate,statuscategorychangedate,issuetype,priority,updated,labels,parent',
            'startAt': start_at,
            'maxResults': max_results
        }
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        issues = response.json().get('issues', [])
        if not issues:
            break
        all_issues.extend(issues)
        if len(issues) < max_results:
            break
        start_at += max_results

    rows = []
    for issue in all_issues:
        fields = issue.get('fields', {})
        assignee = fields.get('assignee')
        if not assignee:
            continue

        parent_field = fields.get('parent')
        parent_summary = parent_field['fields']['summary'] if parent_field and 'fields' in parent_field else ''

        # Raw dates
        raw_created = fields.get('created')
        raw_resolved = fields.get('resolutiondate')
        raw_due = fields.get('duedate')

        task = {
            'assignee_name': remove_emojis(assignee.get('displayName')),
            'project_name': remove_emojis(project_name),
            'issue_key': issue.get('key'),
            'issue_summary': remove_emojis(fields.get('summary')).replace(',', ' '),
            'issue_type': remove_emojis(fields.get('issuetype', {}).get('name')),
            'status': remove_emojis(fields.get('status', {}).get('name')),
            'priority': remove_emojis(fields.get('priority', {}).get('name')),
            'created_date': format_date(raw_created),
            'start_date': format_date(fields.get('statuscategorychangedate')),
            'due_date': format_date(raw_due),
            'resolved_date': format_date(raw_resolved),
            'is_closed': bool(raw_resolved),  # ✅ Closed if resolutiondate exists
            'last_updated': format_date(fields.get('updated')),
            'labels': remove_emojis(', '.join(fields.get('labels', []))),
            'parent_summary': remove_emojis(parent_summary).replace(',', ' '),
            'remarks': ''
        }

        compute_metrics(task, raw_created, raw_resolved, raw_due)
        rows.append(task)

    return rows

# --------------------------- CSV Export --------------------------- #

def export_combined_csv(all_tasks):
    """Export all collected tasks to a single CSV file."""
    filename = os.path.join(CSV_OUTPUT_FOLDER, "Combined_Jira_Performance_Report.csv")
    if not all_tasks:
        print("No tasks found. Skipping export.")
        return
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(all_tasks[0].keys()))
        writer.writeheader()
        writer.writerows(all_tasks)
    print(f"✅ Exported to: {filename}")

# --------------------------- Main Execution --------------------------- #

def run_all_projects():
    """Main orchestrator: loops through all projects, gathers issues, and exports report."""
    try:
        projects = get_projects()
        print(f"🔍 Found {len(projects)} projects.")
    except Exception as e:
        print(f"❌ Failed to fetch projects: {e}")
        return

    all_tasks = []

    for project in projects:
        try:
            print(f"📂 Processing project: {project['name']} ({project['key']})")
            tasks = get_project_issues(project['key'], project['name'])
            print(f"   ↳ Found {len(tasks)} tasks")

            if not tasks:
                tasks.append({
                    'assignee_name': '', 'project_name': remove_emojis(project['name']), 'issue_key': '',
                    'issue_summary': '', 'issue_type': '', 'status': '', 'priority': '', 'created_date': '',
                    'start_date': '', 'due_date': '', 'resolved_date': '', 'is_closed': '',
                    'last_updated': '', 'labels': '', 'parent_summary': '', 'time_to_resolve_days': '',
                    'delay_days': '', 'sla_met': '', 'remarks': 'No task/epic created'
                })

            all_tasks.extend(tasks)

        except Exception as e:
            print(f"⚠️  Failed to fetch issues from {project['name']}: {e}")

    print(f"📦 Total tasks collected: {len(all_tasks)}")
    export_combined_csv(all_tasks)
    print("✅ All project issues exported successfully.")

# Run the script
if __name__ == '__main__':
    run_all_projects()
