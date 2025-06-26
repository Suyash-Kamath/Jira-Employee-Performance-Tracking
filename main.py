import requests
import base64
import os
import csv
from dotenv import load_dotenv
from datetime import datetime

# Load .env file
load_dotenv()

# Jira credentials
JIRA_DOMAIN = 'probustech.atlassian.net'
JIRA_EMAIL = 'suyash.kamath@probusinsurance.com'
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')

# Encode email:token
auth_string = f'{JIRA_EMAIL}:{JIRA_API_TOKEN}'.encode('utf-8')
AUTH = base64.b64encode(auth_string).decode('utf-8')

# Headers
HEADERS = {
    'Authorization': f'Basic {AUTH}',
    'Accept': 'application/json'
}

# Get all projects
def get_projects():
    url = f'https://{JIRA_DOMAIN}/rest/api/3/project/search'
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return [{'key': p['key'], 'name': p['name']} for p in data.get('values', [])]

# Compute performance metrics
def compute_metrics(task):
    try:
        fmt = '%Y-%m-%dT%H:%M:%S.%f%z'
        created = datetime.strptime(task['created_date'], fmt) if task['created_date'] else None
        resolved = datetime.strptime(task['resolved_date'], fmt) if task['resolved_date'] else None
        due = datetime.strptime(task['due_date'], fmt) if task['due_date'] else None

        task['time_to_resolve_days'] = (resolved - created).days if resolved and created else None
        task['delay_days'] = (resolved - due).days if resolved and due else None
        task['sla_met'] = 'Yes' if resolved and due and resolved <= due else 'No'
    except:
        task['time_to_resolve_days'] = None
        task['delay_days'] = None
        task['sla_met'] = 'N/A'

# Fetch issues with full data
def get_project_issues(project_key, project_name):
    url = f'https://{JIRA_DOMAIN}/rest/api/3/search'
    start_at = 0
    max_results = 100
    all_issues = []

    while True:
        params = {
            'jql': f'project={project_key}',
            'fields': 'assignee,summary,status,created,duedate,resolutiondate,statuscategorychangedate,issuetype,priority,updated,labels',
            'startAt': start_at,
            'maxResults': max_results
        }
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        issues = data.get('issues', [])
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

        task = {
            'assignee_name': assignee.get('displayName'),
            'project_name': project_name,
            'issue_key': issue.get('key'),
            'issue_summary': fields.get('summary'),
            'issue_type': fields.get('issuetype', {}).get('name'),
            'status': fields.get('status', {}).get('name'),
            'priority': fields.get('priority', {}).get('name'),
            'created_date': fields.get('created'),
            'start_date': fields.get('statuscategorychangedate'),
            'due_date': fields.get('duedate'),
            'resolved_date': fields.get('resolutiondate'),
            'is_closed': fields.get('status', {}).get('name') == 'Done',
            'last_updated': fields.get('updated'),
            'labels': ', '.join(fields.get('labels', []))
        }

        compute_metrics(task)
        rows.append(task)

    return rows

# Export all issues to CSV
def export_issues_to_csv(tasks, project_name):
    filename = f"{project_name.replace(' ', '_')}_Performance_Report.csv"
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(tasks[0].keys()))
        writer.writeheader()
        writer.writerows(tasks)
    print(f"\n📁 Exported: {filename}")

# CLI Interaction
def run_cli():
    try:
        projects = get_projects()
    except Exception as e:
        print(f"❌ Failed to fetch projects: {e}")
        return

    print("\n📌 Available Projects:")
    for i, proj in enumerate(projects):
        print(f"{i + 1}. {proj['name']} ({proj['key']})")

    try:
        choice = int(input("\n👉 Select a project (1-N): ")) - 1
        if 0 <= choice < len(projects):
            selected_project = projects[choice]
            print(f"\n🔍 Fetching issues for project: {selected_project['name']}")
            try:
                issues = get_project_issues(selected_project['key'], selected_project['name'])
                if not issues:
                    print("⚠️ No issues found.")
                    return
                export_issues_to_csv(issues, selected_project['name'])
                print("\n✅ Employee performance data exported. Ready for Power BI!")
            except Exception as e:
                print(f"❌ Failed to fetch issues: {e}")
        else:
            print("❌ Invalid selection.")
    except ValueError:
        print("❌ Please enter a valid number.")

# Run
if __name__ == '__main__':
    run_cli()
